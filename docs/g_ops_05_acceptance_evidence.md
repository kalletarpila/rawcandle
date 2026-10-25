# G-OPS-05 acceptance evidence

**COMPLETE — read-only investigation and exact retirement proposal.** Operational
cleanup, historical reconciliation and retention-policy changes were not authorized
or performed. Starting HEAD `73dcaa92977e183060402cca7652ef634c3e1853`, branch
`chore/ignore-backups`; final HEAD is the local report commit, recorded exactly in
ignored `temp/g_ops_05/commit_receipt.json`. Push: **NO**.

The two scope clarifications govern the result: investigate the real methodology
transition, then prioritize EC rebuildability and the **whole Analysis** recovery
obligation. No generic StockCore/DC dependency was introduced. No applicable
RawCandle AGENTS.md exists in this checkout/ancestors; StockCore remains outside
operational scope. The prior G-OPS-04 reports/evidence were reviewed, not rewritten.

## Preserved production and ownership

Preflight verified the expected HEAD, branch and 12 existing worktree entries,
24 image identities, single links, regular-file/ownership safety and empty or
absent WAL state. Device/inode/size/mtime/ctime witnesses match G-OPS-04's SHA-256,
quick_check and schema qualifications. Those expensive 291 GB full-file hashes
were reused under unchanged content-identity witnesses, not needlessly repeated.
All 24 images were inspected read-only through their actual tables and metadata;
no unsafe image branch was forced open or restored over production.

Host process/open-file/kernel-lock inspection found no competing EC/source or
provider workflow owning the images; the idle UI was preserved. Analysis used
short read-only statements without holding scheduler/Production locks. Current
canonical heads remain aligned through October 23; the publication journal is
COMPLETED, postflight PASSED, recovery NOT_REQUIRED. October 25 Fundamentals
FULL_WORKFLOW failure remains a separate blocker with Production not invoked;
EC skipped with NO_EC_CATCHUP_NEEDED.

Source, EC, DC, Fundamentals, StockCore and operational Analysis main files were
not written. Read-only SQLite readers can update/create transient SHM/empty WAL
reader metadata; no committed data or existing backup was deleted/checkpointed.
The original publication journal changes and all other pre-existing work remain
untouched. Source/forecast configuration, installed cleanup script and the
G-OPS-04 hold are fingerprinted before/after and remain unchanged. Scheduler times
and enabled states were not modified. No StockCore code/database was imported,
modified or made a runtime dependency.

## Reproduction and compact evidence

`reproduce.py` used the existing strict checker, explicit active taxonomy/V2 and
the original 25 dates. Only its per-process diagnostic example-output limit was
raised to capture every key/value; tolerance and comparison rules were unchanged.
The exact **15,269 semantic + 2,033 lineage = 17,302** differences reproduce,
concentrated in synthetic/index groups; ticker/group-signal differences are zero
in that window. Nineteen dates fail, latest six pass. The full key/value dataset
has **2,033 group/date records**, not 17,302 different securities.

Runtime evidence under existing ignored `temp/g_ops_05/` includes:

| Evidence | Purpose |
|---|---|
| `exact_mismatches.json`, `parity_full.json`, `reproduction_summary.json` | Exact requested-scope differences, current comparison versions and aggregates |
| `snapshot_states.json`, `representative_rows.json`, `definition_fingerprints.json` | Every image's fact/version fingerprints, exact old/current samples and code/definition identities |
| `input_repair_receipts.json`, `v1_preservation.json` | Relevant existing source inserts and accepted V1 invariants |
| `whole_database_states.json`, `non_ec_owner_qualification.json` | All 50 tables in each image; current non-EC/manual/ledger coverage |
| `current_non_ec_delta.json`, `non_ec_delta_qualification.json` | Exact 34-table non-EC supplement and independent isolated patch checks |
| `current_ec_control_state.json`, `current_ec_latest_window.json`, `ec_exact_state_qualification.json` | Complete EC controls/sequences and exact current fact-tail restoration |
| `compact_research_versions.json`, `compact_research_qualification.json` | All 115 disappeared research rows, original values/metadata and exact restore checks |
| `recovery.json`, `recovery_bundle_manifest.json` | Bounded actual-owner recovery drill, limitations and artifact bindings |
| `backup_recovery_decisions.json`, `retirement_proposal.json` | Per-image obligations, alternatives, expiration conditions and non-executable proposal |

An initial broader guard examined 310 shared-history dates and found additional
pre-window group-universe/lineage differences. It is preserved separately in
`full_history_summary.json`, not mixed into the requested 19-date reproduction.
The July 31 ticker lineage difference and pre-window group-type count differences
mean ticker/group-signal parity is **not** asserted globally clean. Their detailed
historical-contract branch was not expanded after the storage scope clarification;
current retained state already preserves them and current DC supplies projection
inputs. No complete historical arithmetic audit is claimed.

## Recovery qualification

The actual pre-write owner uses SQLite online backup; recovery is controlled
Analysis restoration/replay, not an automatic multi-database rollback. Existing
`assess_backup_schema_compatibility` qualified the retained image. One isolated
EC restore copied the 16 EC tables, verified exact initial table digests, schema,
foreign keys and integrity, and used the existing four loaders for only six dates
against the image's matching DC source tables. No live backfill command ran.

Complete current EC fact payload/lineage equality passed after replay across all
four tables. Separate base-prefix plus recorded tail checks passed **all columns,
including original publication clocks**. Control metadata and sequence state are
captured explicitly; they are not assumed reconstructible from numeric facts.
Additional non-EC drills restored all excluded/blackout/results-metadata/relevance
run records and representative large-table rows. The final bounded file was
**156,794,880 bytes** and was removed after qualification. No full 13 GB restore
copy or new permanent full backup was created.

The non-EC supplement was generated by a full ordered comparison of every row in
all 34 non-EC tables between image 24 and current production. Its actual insert,
delete, update and clock-only patch operations were independently applied in
memory SQLite tables; all **109,146** resulting affected rows matched current
rows exactly, with integrity checks. This supplements the existing full image;
it is not a claim that a 231 KB extract can restore Analysis alone.
The 115 historical research-row versions were each restored exactly in isolation.
Earlier mutable generated-analysis versions are not silently declared byte-equal
or all reproducible from today's raw-price vintage; no current owner requires
those intermediate whole-image states after accepted replacement.

A complete independent **full Analysis** restoration to a second 13 GB database
was deliberately not performed. The qualification combines the existing coherent
full-image hash/integrity proof, all-table inspection, complete non-EC logical
comparison and bounded application/patch restoration. It does not certify an
off-host whole-system disaster restore, source database recovery or every prior
raw-observation vintage. The latest full image remains required until a qualified
general replacement exists; adopting/renaming it does not free its physical bytes.

## Focused validation and outcome

**73 focused tests passed**:

- Existing EC/DC parity and field-policy tests.
- Membership weighting and effective-weight integration tests.
- Fixed-anchor Datacenter index persistence tests.
- All G-OPS-04 EC retention invariants, including unresolved-hold protection.

Runtime assertions also verified exact mismatch classification, version/vintage
comparisons, all-image census/identity reconciliation, full V1 preservation,
research archive round-trips, current-state supplements and temporary-copy cleanup.
No new production implementation or maintained fixture was needed for this
investigation. `git diff --check` and task-report link/manifest checks passed.
**Full suite: NO.**

**Provider calls: 0. Operational publications/backfills: 0. Backup deletions: 0.**
Backup count/allocation remains **24 / 291,597,950,976 bytes**. Decisions:
**1 RETAIN_REQUIRED / 0 RETAIN_TEMPORARILY / 23 RETIRE_CANDIDATE /
0 BLOCKED_UNCERTAIN**. Proposed reclamation in a separately authorized cleanup:
**278,384,205,824 bytes**. All 21 historical candidates are included.

Recommended next phase: exact candidate cleanup plus explicit adoption of the
existing general Analysis point and preservation of the compact bundle; qualify
hold release under clarified recovery obligations without requiring a historical
repair project. Do not clear the hold in G-OPS-05. Until that decision, the existing
hold continues to permit backup accumulation. Historical mirroring/invalidation
policy, the separate Fundamentals failure and the absent August rollback reference
remain distinct follow-up matters, not authority to change production now.
