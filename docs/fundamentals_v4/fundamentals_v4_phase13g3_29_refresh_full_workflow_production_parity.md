# Phase 13G.3.29 Refresh Full Workflow Production-Parity Acceptance

## Scope

Phase 13G.3.29 proves the compact market source architecture through the real Refresh Full Workflow from Preview through terminal Production behavior.

The permanent fixture suite enters through `FundamentalsAdminUIService.full_workflow()` and runs the real Preview, copy-only Test, Production candidate builders, publication journal, postflight, rollback, recovery, and terminal cleanup. Sharadar transport is injected and fixture-only; the suite makes no Internet requests and does not sleep for request pacing.

Taxonomy remains FULL_SQLITE_BACKUP and is outside this acceptance claim for direct live reads.

## Fixture

The fixture has two companies and securities, complete ARQ/MRQ histories, eight canonical TTM requirements, active Sector/Industry classifications, active DC taxonomy membership, one corrected split, and 630 price rows. Coverage deliberately includes one `PRICE_FOUND`, one `NO_MATCHING_VALID_PRICE`, and six `NO_CUTOFF` results. This reaches the real V2, RP, RV, dependency validation, and postflight paths.

Observed fixture sizes were:

| Database | Bytes |
| --- | ---: |
| Provider after publication | 118,784 |
| Canonical | 266,240 |
| Analysis | 458,752 |
| Market source | 73,728 |
| Taxonomy source | 20,480 |
| Compact market bundle | 86,016 |

The compact fixture can be slightly larger than its tiny market source because SQLite page overhead dominates at this scale. The real architectural assertion is that neither Test nor Production copies the full market source and that the compact bundle is not a publication role.

## Acceptance Proof

The success path proves:

- Test uses `STABLE_SOURCE_BUNDLE` for market and `FULL_SQLITE_BACKUP` for taxonomy.
- Test persists `read_only_source_binding.json`, and Production loads it by exact Test run ID and evidence path.
- Contract version, as-of date, canonical semantic binding, market semantic fingerprint, coverage counts and status fingerprints, and taxonomy version/fingerprint match between Test and Production.
- Ephemeral Test and Production bundle paths differ while their semantic contracts match.
- Provider, canonical, and analysis are the only backup, journal, publication, and rollback roles.
- The analysis candidate uses the bound Production market bundle and taxonomy copy; pre-publication validation and published-generation postflight both pass.
- Terminal cleanup removes candidate databases, the compact market bundle, and the taxonomy copy while retaining lightweight reports, source-binding evidence, and terminal journal evidence.

No unexpected large temporary database was created. The successful workflow took approximately 4 seconds by durable stage timestamps; the five-case focused suite took 28.74 seconds.

## Fault Proof

The stale-market case mutates a required price row after Test. The stale-taxonomy case changes the active taxonomy version and source hash after Test. Both return `REFRESH_TEST_SOURCE_BINDING_STALE` before analysis candidate creation, backups, journal creation, or live publication. Direct live provider/canonical/analysis hashes remain unchanged.

The post-boundary failure case injects failure after provider replacement. The journal reports `ROLLED_BACK`, restores all three OLD provider/canonical/analysis roles, and never treats market or taxonomy as restore roles. OLD-generation table content matches its pre-workflow semantic fingerprints, and each restored live file matches its journal-verified backup SHA-256.

The crash case leaves a nonterminal journal after provider replacement. The real production write guard restores the complete OLD generation, marks the journal `RECOVERED`, raises retry-required, and does not finish the NEW generation. Recovery again verifies both OLD semantic content and exact backup fingerprints before terminal candidate/source cleanup.

## Orchestration Defect

The acceptance suite exposed a real failure-path defect: persisted `retry_authorization` is redacted to a string, while Full Workflow assumed it was a mapping. That secondary exception obscured a valid stale-source rejection. Full Workflow now type-checks persisted retry metadata and falls back to the child result's already-derived retry flags. A focused regression locks this behavior without weakening stale-source or publication guards.

## Remaining Gap

Taxonomy is still copied under the established `FULL_SQLITE_BACKUP` contract. This phase does not authorize direct locked reads from live taxonomy state and does not migrate any runtime path to that future model.
