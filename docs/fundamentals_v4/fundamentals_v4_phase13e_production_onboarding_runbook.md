# Fundamentals V4 Phase 13E Production Onboarding Runbook

Phase 13E must not activate production onboarding until the Phase 13D.2 Outcome B blockers are closed on copies.

## Required Preconditions

- Clean Git worktree at the reviewed deployment commit.
- No Scheduler or Fundamentals writer process is active.
- Production paths match the Phase 13C protected path contract.
- Fresh production inventory has hashes, sizes, mtimes, quick checks, active package pointer, active operational universe pointer and active Relative Valuation pointer.
- Adequate free storage exists for online copies, backups, journals and artifacts.
- The Sharadar API key is loaded through repo `.env` or process environment and is never printed, passed on the command line or serialized.
- Phase 13D.2-equivalent replay has `raw_equal=true` and deterministic UI-facing report content, not merely deterministic downstream economics.

## Source Acquisition

For a ticker such as SNDK:

1. Resolve stable identity before importing rows.
2. Prefer the verified managed source archive.
3. Use a bounded Sharadar request only if archive rows are absent and the API contract supports ticker-scoped acquisition.
4. Stage API or archive content into an isolated directory first.
5. Validate schema, identity, duplicates, revisions, numeric fields, periods and ten-year policy.
6. Never write provider content directly into production.

For SNDK specifically, permaticker `643888` and CIK `0002023554` must remain distinct from predecessor `SNDK1` / permaticker `197210`.

For AREB specifically, production activation is blocked until taxonomy membership is resolved through evidence. Phase 13D.2 left AREB as `TAXONOMY_REVIEW_REQUIRED`.

## Apply Order

Production activation must use one confirmed, lock-protected operation:

1. Create online backups for every database that may change.
2. Stage provider observations.
3. Persist canonical company, security, aliases and provider identity.
4. Apply operational universe membership.
5. Reconcile canonical quarters.
6. Rebuild TTM.
7. Rebuild and activate the full coherent Operating-Income V2 package.
8. Rebuild full-universe Relative Position.
9. Mark existing Relative Valuation incompatible when universe or economic taxonomy fingerprints changed.
10. Generate Snapshot only with dependency-aware readers that explicitly suppress or label incompatible Relative Valuation before the manual refresh.

Relative Valuation refresh remains a separate explicit manual operation:

1. Confirm the full-universe refresh.
2. Persist and activate the new copy/prod snapshot.
3. Re-check dependency compatibility.
4. Run a second identical refresh and require genuine `NO_CHANGE`.

## Taxonomy

If an existing valid taxonomy membership is found, connect the stable canonical/provider identity to that entity without creating duplicate memberships. Use schema-valid alias or audit rows.

If no valid membership exists, create a preview only. Do not invent a peer group to make onboarding succeed. Ambiguous membership must remain `TAXONOMY_REVIEW_REQUIRED`.

Presentation-only taxonomy changes may leave economic results compatible. Peer-group, applicability or membership changes are economic dependency changes and must force downstream compatibility checks.

## Rollback

Failure recovery must be proven at these boundaries before production activation:

- provider staging validation;
- provider import;
- identity and alias writes;
- operational universe write;
- canonical rebuild;
- TTM rebuild;
- downstream package calculation;
- Relative Position persistence;
- package activation;
- Snapshot assembly;
- taxonomy dependency update;
- separate Relative Valuation refresh and activation.

If any boundary fails, restore every modified database from verified backups and prove no partially onboarded ticker is presented as successful.

Activation-only rollback is not sufficient. Phase 13D.2 did not prove the full failure-injection matrix, so Phase 13E must use verified full online backups of every writable database and prove exact restoration, quick_check, foreign-key checks, active pointers and dependency fingerprints before replacing any failed copy or production file.

## Phase 13D.2 Carry-Forward Blockers

Phase 13D.2 completed the economic copy-only rebuild and manual Relative Valuation refresh, but production remains blocked by:

- AREB taxonomy ambiguity: `TAXONOMY_REVIEW_REQUIRED`.
- Pre-refresh Snapshot/UI rendering still produced reports with Relative Valuation content although the dependency state was `OPERATIONAL_UNIVERSE_MISMATCH`.
- Snapshot report content fingerprints were not deterministic because the technical source-state includes run-local audit fields.
- Full multi-database failure injection and exact restoration remain unproven.
- Full onboarding second-apply `NO_CHANGE` remains unproven.

Reader corrections already established by Phase 13D.2 must remain in place: Relative Valuation source input excludes upstream Relative Position `snapshot_id` and filing valuation `calculated_at_utc` because those are run-local metadata, not economic source content.

## Required Final Evidence

Production Phase 13E must leave artifacts equivalent to Phase 13D.1 plus:

- complete manual Relative Valuation refresh evidence;
- restored Snapshot/UI reader compatibility;
- full failure-injection matrix;
- second-run deterministic evidence from independently created equivalent starting copies;
- second production apply `NO_CHANGE` evidence;
- production postflight showing unchanged unrelated databases and reports.
- deterministic pre-refresh and post-refresh Snapshot report content after stripping or otherwise controlling run-local source-state metadata.
