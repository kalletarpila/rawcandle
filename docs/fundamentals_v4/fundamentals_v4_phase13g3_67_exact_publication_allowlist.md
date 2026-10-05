# Phase 13G.3.67: Exact Publication Allowlist

Date: 2026-10-05

## Decision and Scope

Phase 13G.3.66 stopped before production application: the journaled writer
could only select the 278-row recent-open cohort, not the reviewed 60 identities.
Lower-level quarter-key filtering was not a substitute for the production writer.
This phase extends that existing writer; it does not apply the 60 cases live.

Exact allowlist mode constrains scope only. It does not authorize a publication result, alter resolver semantics, or convert ambiguous/open cases into verified results.

An explicit empty allowlist is a no-op and must never fall back to the default recent-open backlog.

## Entry Contract

`run_backlog_drain(exact_quarter_allowlist=...)` accepts a collection of
`(company_id, fiscal_year, fiscal_quarter)` identities. `None` retains ordinary
recent-open drain selection. An explicit empty collection returns `SKIPPED`
with `NO_ELIGIBLE_ALLOWLIST_ITEMS`; it creates no candidate, backup or activation.
Existing recovery checks still precede a no-op on an apply invocation.

Normalization accepts positive SQLite-range company IDs, years 1 through 9999,
and Q1 through Q4. Integer strings and quarter case/whitespace normalize;
booleans, floats, malformed shapes and normalized duplicates are rejected
before candidate creation. Sorted canonical keys serialized as compact JSON
produce the SHA-256 allowlist fingerprint. No ticker-derived identities are used.

Exact mode cannot be combined with `NEW_THIS_REFRESH`. No retry cap is used
as a substitute for allowlisting. Default candidate enrichment retains its
100-quarter retry cap, uncapped new quarters, 60-day horizon and ordering;
the existing manual backlog drain remains uncapped when no allowlist is supplied.

## Locked Selection and Existing Apply Path

For an apply invocation, authoritative exact selection happens inside the
existing production/scheduler lock, after journal recovery and active-generation
drift checks. Indexed natural-key queries inspect only supplied identities.
Dry-run classification is read-only and does not fetch SEC evidence.

Report-only classifications are `SELECTED_OPEN`, `NO_LONGER_OPEN`,
`NOT_IN_CURRENT_SCOPE`, `CURRENTLY_AMBIGUOUS`, `CURRENTLY_VERIFIED`,
`IDENTITY_MISSING` and `ERROR`. Existing AMBIGUOUS and VERIFIED rows are skipped.
These are not new statuses in publication tables. Only SELECTED_OPEN keys
continue to the existing resolver.

The exact path is:

1. Read-only fresh `enrich_database(apply=False)` on selected keys.
2. Exclude fetch-error keys from the apply set and report their errors.
3. Revalidate the same candidate keys and seal fetched filing inputs.
4. Invoke the same `enrich_database(apply=True)` / `apply_resolution` path on
   successfully classified keys with those frozen inputs.

A fetch error is ERROR / not selected for apply, not an authority write.
The run records `errors` and `skipped_error_natural_keys`; no new production
status or automatic retry policy is introduced. No-candidate and ambiguous
successful resolutions continue through existing apply semantics and remain open.

Frozen inputs are immutable `SecFiling` objects, including parent accession,
acceptance timestamp, primary text and bounded linked-exhibit context/hashes.
The cache key includes CIK, calendar-year bound and date scope. Apply cannot
fetch again or obtain a different filing set; a missing frozen input fails closed.
Evidence freezing does not replace resolver ranking or authority decisions.
Preview classifications are not treated as authorization, and the existing
apply decision remains authoritative. `None` does not use this two-pass adapter.

Selected, previewed, enriched and applied keys have subset assertions. Missing
preview results, unexpected results, candidate-state drift or expanded apply
scope prevent activation. Chunking supports more than 200 exact keys without
falling back to recent-open selection. Final open counts are limited to selected
keys; unrelated historical publication rows are not scanned for enrichment.

## Generation, Journal and Recovery

The existing candidate copy, SQLite verification, verified backups, journal,
immutable-generation activation, postflight, rollback and cleanup remain in use.
No active-generation database is edited directly.

Exact run evidence and the journal record scope mode, normalized keys/count,
fingerprint, selected keys/count, skipped counts, enriched/applied keys,
applied count and fetch-error keys. Applied count means existing authority apply
attempts, not new VERIFIED results; `new_verified` remains separate.
Structured result JSON holds per-key details instead of dumping them into
operator Markdown. Default journals do not acquire exact-mode fields.

Recovery preserves scope evidence. The first recovery invocation restores the
old generation and requires a retry, as before. A subsequent exact-journal retry
must provide the same normalized allowlist fingerprint; omission or a different
scope fails before selection. A recovered exact scope is never widened to the
ordinary backlog. The fence remains until a successful matching-scope publication;
a matching no-op does not erase recovery evidence. Completed journals do not
restrict later ordinary drains. Existing rollback machinery is unchanged.

## Operator CSV

The existing CLI accepts `--exact-allowlist PATH`. It reads only
`company_id`, `fiscal_year`, `fiscal_quarter`; additional review columns are not
authority or selection inputs. Required headers, malformed rows and duplicates
are validated. A header-only CSV is explicitly empty.

Count, scope mode and fingerprint are printed to stderr before execution;
stdout remains the existing result JSON. `--apply --confirm-production` is still
required for publication. No CLI apply command was executed against production.

The Phase 13G.3.66 CSV parses to 60 unique keys: 28 prior UNRESOLVED,
32 prior NOT_FOUND, zero AMBIGUOUS and zero C8 cases. Its fingerprint is
`4b69d8500733c1d3e3d5219458bf070dc5c8fb6b99f4082e3241413c9a99ce4e`.
This validates the reviewed artifact, not fresh live resolver eligibility.

## Focused Validation

Targeted command:

```bash
venv/bin/python -m pytest -q tests/test_publication_exact_allowlist.py tests/test_candidate_publication.py tests/test_publication_backlog_drain.py tests/test_result_publication_authority.py
```

Result: 72 passed (40 exact-mode tests and 32 existing regression tests).

The exact-mode tests cover normalization, CSV parsing, empty/default behavior,
current VERIFIED/AMBIGUOUS protection, unknown and stale identities, unique and
no-candidate results, fetch-error exclusion, scope assertions, in-lock selection,
multi-chunk scope, pre-publication failure, post-boundary rollback, three crash
boundaries, first recovered retry, same-scope recovery and CLI confirmation.

The accession/exhibit regression deliberately makes a second fetch return
different evidence. It proves metadata/primary/exhibit are fetched once,
apply receives the identical frozen accession and context, persisted exhibit
hashes match precheck, and higher-ranked issuer authority is preserved by the
existing apply function. Separate conflict tests retain ordinary ambiguity.

A production-shaped fixture rehearsal at
`/tmp/rawcandle_13g367_rehearsal_bp3wjgg5/root` exercised the actual writer:
six allowlisted identities, two selected/apply attempts, one new VERIFIED and
one NOT_FOUND, valid PARTIAL workflow, COMPLETED journal and successful immutable
activation. The larger universe included unrelated open rows and protected
VERIFIED/AMBIGUOUS rows. Unrelated authority rows and canonical financial/identity
content remained unchanged, provider/analysis bytes and old generation hashes
were preserved, all postflight quick checks passed with zero foreign-key failures,
and the candidate lane was cleaned. All SEC data was injected fixture evidence.

Compile/import checks and `git diff --check` passed. The full suite
was not run. No fresh SEC network verification or live 60-case application was
performed; this phase grants no production result authorization.

## Production Safety

No production publication, drain, Refresh or scheduler was executed. Production
authority/financial DBs, active generation, Review Queue, journal and scheduler
configuration were not changed. Existing unrelated dirty runtime and research
files are excluded from the source/tests/docs commit. No backups were deleted.
Production remains on `publication_drain_20261005T064921Z_43a1e040`.
Read-only SHA-256 comparison against the Phase 13G.3.66 STOP evidence confirmed
all three production role DBs, pointer, journal, Review Queue and scheduler
configuration unchanged.
