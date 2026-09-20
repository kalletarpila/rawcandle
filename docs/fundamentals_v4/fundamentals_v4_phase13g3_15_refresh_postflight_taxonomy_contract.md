# Phase 13G.3.15: Refresh Postflight Taxonomy Contract

## Outcome

Refresh Production now consumes the full-V2 Admin result's authoritative
`active_taxonomy` contract in both candidate validation and published postflight.
Missing, malformed, wrong-domain, or mismatched dependency evidence fails with a
controlled Refresh validation error. No live Refresh was run in this phase.

ARQ/MRQ downstream overlay remains intentionally deferred.

Read-only market/taxonomy source-copy optimization remains intentionally deferred
to a separate architecture phase.

## Root Cause

The low-level `rebuild_v2_analysis()` result contains `taxonomy_dependency`.
`run_full_v2_downstream()` deliberately maps that value to the Admin-facing field
`active_taxonomy`. Its returned keys are:

`action`, `active_taxonomy`, `as_of_date`, `candidate_analysis_db`,
`fingerprints`, `invocation_counts`, `package`, `relative_position`,
`relative_valuation`, `status`, and `validation`.

Refresh Production passed this Admin result to `_postflight()`, whose consumer
still attempted `analysis_result["taxonomy_dependency"]`. The exact object that
raised the `KeyError` was therefore the valid Admin full-V2 result, not the raw
rebuild result. The required dependency already existed under
`active_taxonomy`; no placeholder was needed.

Test on copies consumed the Admin contract and reported `active_taxonomy`, but it
did not execute the live publication postflight. Phase 13G.3.14 did not introduce
the naming mismatch; it exposed the pre-existing postflight consumer drift by
allowing Production to reach POSTFLIGHT for the first time.

## Contract Repair

`_required_taxonomy_dependency()` now requires non-empty `domain`, `version`, and
`semantic_fingerprint` values from `active_taxonomy`, and requires the domain to
be `dc_ecosystem`. `_validate_analysis_generation()` passes that exact dependency
to the existing full-V2 `validate_rebuild()` routine.

The validation runs twice:

1. Before backup and publication, against the analysis candidate and the same
   provider/canonical/market/taxonomy copies used to build it.
2. After publication, independently against the live published generation.

Missing or malformed evidence raises
`REFRESH_ANALYSIS_TAXONOMY_DEPENDENCY_MISSING_OR_MALFORMED`. Taxonomy lineage
mismatch raises `REFRESH_ANALYSIS_TAXONOMY_DEPENDENCY_MISMATCH`. A raw missing-key
exception can no longer authorize or accidentally enter publication.

Deterministic checks duplicated before publication are dependency shape/domain,
analysis-embedded RP taxonomy identity, active copied taxonomy identity, V2
package lineage, RV source/result lineage, and candidate reader validation.

Checks that necessarily remain post-publication are live production-path
fingerprints, the published provider Refresh-state row, canonical identity and
first-public invariants at live paths, the published analysis reader, and the
provider/canonical/analysis cross-role generation match. Postflight was retained;
candidate validation does not replace it.

## Production-Parity Principle

For every future multi-stage Fundamentals Admin workflow, at least one
fixture-sized acceptance test must pass the actual producer's runtime object
through the real Production orchestration and consumer boundary:

`candidate builders -> dependency validation -> publication -> postflight -> semantic commit`

Unit tests may isolate expensive internals, but must not replace the producer's
public result with a hand-authored consumer fixture when testing a producer/
consumer contract. Deterministic postflight prerequisites must be checked before
the publication boundary wherever technically possible, and the published
generation must still be independently validated afterward.

The Phase 13G.3.15 parity test uses the real Refresh Production call path, real
provider-history replacement builder, real canonical fresh-rebuild builder,
real Admin `run_full_v2_downstream()` result mapping, real candidate dependency
consumer, durable three-role publication, and real Refresh `_postflight()`
consumer. The expensive analysis calculation engine and deep analysis-DB
validator are fixture-isolated; the engine produces a tiny analysis DB and its
raw result is mapped by the real Admin wrapper. The validator fixture records
and verifies calls against both the candidate path before publication and the
live analysis path after publication. The test consumes the real provider,
canonical, and Admin analysis result objects, reaches terminal `COMPLETED`,
proves the published provider/canonical financial value, and advances the
fixture watermark only after postflight.

## Rollback Reporting

Journal role records now preserve two independent facts:

- `candidate_replacement_verified`: this candidate was physically installed and
  verified at its live path;
- `rollback_restoration_verified`: the OLD backup was restored and verified for
  this role.

Reports show actual role lists and counts for live replacements and rollback
restorations, plus `Net published generation changed`. A pre-publication failure
shows zero replacements. A partial publication shows its exact prefix. A complete
rollback shows the physical write activity while correctly retaining candidate,
not published, ticker semantics.

## Live Safety Verification

The latest journal is terminal `ROLLED_BACK` for run
`20260920T160614Z_refresh_fundamentals_0e0c9a7e2477_production_a4bd3d37`.
All three role records are `OLD_GENERATION_RESTORED`; journal postflight state is
`OLD_GENERATION_VERIFIED`. The provider has no `sharadar_refresh_state` table, so
the published Refresh state remains `BOOTSTRAP_BASELINE` and the published
watermark remains absent. BNC has zero provider observations and zero canonical
quarters. No nonterminal journal blocks writers.

The restored live files exactly match their verified online-backup fingerprints:

| Role | Restored/backup SHA-256 | Size |
| --- | --- | ---: |
| provider | `0f581aa600191e2bfb1ae0094442af30e12ef4ef228eba5b4a5133042b7a33f5` | 958,828,544 |
| canonical | `4abb19212f83bf1fe0f011d6f1ca963db9c970609e22bdbb0be29c0768a40066` | 656,252,928 |
| analysis | `525c94637ff315758d3b4dc1472ec051eb674823c40d22c32e35c563eeaa23aa` | 904,691,712 |

These physical hashes differ from the pre-publication files because SQLite online
backup rewrote page layout. The journal records the old source hashes separately
and proves each restored live file equals its verified OLD-generation backup.

## Cleanup And Retention

The terminal rollback has no run-owned provider/canonical/analysis candidate,
market snapshot, taxonomy snapshot, WAL, SHM, or temp file remaining. Candidate
and source-copy cleanup is complete.

Three verified OLD-generation rollback backups remain under
`backups/fundamentals_admin_production/<run-id>`:

- provider: 958,828,544 bytes;
- canonical: 656,252,928 bytes;
- analysis: 904,691,712 bytes;
- total: 2,519,777,280 bytes including directory accounting.

Their hashes are listed above. They were not deleted because the established
policy requires operator acceptance before removing rollback backups.

## Files Changed

- `rawcandle/fundamentals/admin/refresh_production.py`
- `rawcandle/fundamentals/admin/publication_journal.py`
- `tests/test_fundamentals_admin_refresh_production.py`
- this report

## Validation

- Focused Refresh Production/full-V2 suite: `66 passed`.
- Broader Refresh Preview/Test/Production/full-workflow/full-V2/Admin UI suite:
  `166 passed`.
- Changed Python modules and tests passed `py_compile`.
- `git diff --check` passed.

The scheduler service and timer remained `inactive/dead`. This phase executed no
live Preview, Test on copies, Production update, or full workflow.
