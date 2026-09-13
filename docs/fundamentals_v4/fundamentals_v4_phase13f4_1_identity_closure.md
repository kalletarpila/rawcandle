# Phase 13F.4.1 Structural Package And Dependency Identity Closure

Outcome: `OUTCOME C - CURRENT PERSISTENCE ARCHITECTURE CANNOT SAFELY VERSION STRUCTURAL-AWARE PACKAGES; REDESIGN REQUIRED`.

Date: 2026-09-13.

## Scope

Phase 13F.4.1 inspected the existing Operating-Income V2 package persistence, activation,
reader, dependency and Relative Valuation contracts after Phase 13F.4 correctly stopped before
production writes.

No production database write, schema migration, active pointer change, report regeneration,
network request, scheduler change or UI change was performed.

## Identity Architecture Map

The current package identity architecture separates formula/model identity from some package
metadata, but the persisted economic rows are not fully package-namespaced.

| Layer | Persisted identity | Row namespace | Reader validation | Structural impact |
| --- | --- | --- | --- | --- |
| Formula/model map | `model_manifest_json` in `operating_income_v2_package_manifest` and `fundamentals_active_model_family` | Formula fingerprints | `activation.assert_v2_active` and `ParallelModelRepository.assert_v2_bundle` | May remain unchanged because formulas do not change |
| Package manifest | `operating_income_v2_package_manifest.persistence_fingerprint` plus economic/physical fingerprints | One current manifest per family | Active assertion requires current manifest fingerprint to equal active pointer | Needs structural dependency identity, but metadata alone is insufficient |
| Manifest history | `operating_income_v2_package_manifest_history.persistence_fingerprint` | Manifest only | `package_manifest(fingerprint)` can read history row | Historical rows are not enough to read old economics |
| Score | `score_result.model_fingerprint` | Shared by formula fingerprint | Readers select by model fingerprint | Structural apply deletes/replaces rows for the same model |
| Lifecycle | `lifecycle_revised_result.model_fingerprint`, `history_mode` | Shared by formula fingerprint | Readers select by model fingerprint and history mode | Structural apply deletes/replaces rows for the same model |
| Valuation | `valuation_revised_result.model_fingerprint`, `history_mode` | Shared by formula fingerprint | Readers select by model fingerprint and history mode | Structural apply deletes/replaces rows for the same model |
| Delta | `fundamental_delta_package.model_fingerprint`, `history_mode` | One package per model/history | Readers join through current model package | Structural apply deletes/replaces package for same model/history |
| Diagnostics | `diagnostic_flag_package.model_fingerprint`, `history_mode` | One package per model/history | Readers join through current model package | Structural apply deletes/replaces package for same model/history |
| Relative Position | `relative_position_snapshot.snapshot_id` | Snapshot-id namespaced, but active pointer is per model | Readers use active snapshot | Coexistence is structurally possible for RP snapshots |
| Relative Valuation | `relative_valuation_snapshot.snapshot_id` | Snapshot-id namespaced | RV repository uses active snapshot or explicit snapshot | Coexistence is structurally possible for RV snapshots |
| Generic dependencies | `fundamentals_result_dependency` | One row per consumer family/object/object id | Compatibility helpers inspect universe/taxonomy fields | Existing contract does not include structural identity fields |
| RV dependencies | `relative_valuation_snapshot_dependency` | One row per RV snapshot | Compatibility helper checks universe/taxonomy fields | Existing contract does not include package/structural fields |

## Blocking Finding

The Operating-Income V2 package apply path is not an immutable package-store architecture.
It archives manifests, but it mutates shared result tables behind stable model identities.

The relevant apply behavior is:

- score rows are deleted by `score.MODEL_FINGERPRINT`;
- lifecycle rows are deleted by `lifecycle.MODEL_FINGERPRINT`;
- valuation rows are deleted by `valuation.MODEL_FINGERPRINT`;
- delta packages are deleted by `delta.MODEL_FINGERPRINT`;
- diagnostic packages are deleted by the active diagnostic model fingerprint;
- relative-position active/snapshot rows are deleted by `relative_position.MODEL_FINGERPRINT`.

This means a structural-aware package apply can replace the economic rows used by the old
production package while old package metadata remains in manifest history. The historical manifest
would still be readable, but it would no longer point to a separately persisted old row generation.

Adding structural dependency metadata alone would therefore create a false sense of safety:

- old and new package manifests could be distinguished;
- old and new row generations could not both be read through the current OI V2 row schema;
- pointer rollback could not be proven coherent without restoring the full database;
- `NO_CHANGE` detection could compare metadata while still missing row-generation ambiguity;
- readers could not prove from persisted metadata alone that an old manifest is backed by old rows.

## Why A Small Additive Migration Is Not Enough

The prompt requires the old production package and the new structural-aware package to coexist
unambiguously, with readers and rollback checks able to distinguish them from persisted metadata
alone. The existing row schema does not carry a package-generation key across Score, Lifecycle,
Valuation, Delta and Diagnostic result rows.

An additive dependency table could record:

- `ECONOMIC_STRUCTURAL_BREAK_CONTRACT_V1`;
- structural package, event and source fingerprints;
- canonical/TTM source fingerprints;
- operational-universe and taxonomy dependencies;
- calculation as-of semantics.

However, that would not make old rows coexist with new rows. It would only describe the latest
mutable row generation. The old production package would remain dependent on a full-database backup
for rollback, not on an independently selectable package namespace.

The smallest safe redesign must introduce one of these larger architectural changes:

- immutable package-scoped row namespaces across every OI V2 result table and reader; or
- append-only replacement tables for structural-aware package generations with readers that select
  by package identity; or
- a formally documented architecture where OI V2 package activation is always a full-database
  restore boundary and archived manifests are explicitly metadata-only, not activatable packages.

The first two options require broad reader, writer, activation, validation, rollback and test
changes. The third option fails the Phase 13F.4.1 requirement for old/new package coexistence.

## Relative Valuation

Relative Valuation is closer to the required shape because snapshot results are keyed by
`snapshot_id`, and multiple snapshots already coexist. Its dependency contract still lacks explicit
package and structural dependency fields, but that gap is correctable only after the upstream OI V2
package identity is safe. Extending RV first would not solve the upstream package-generation
ambiguity.

Current active RV production state remained:

- active snapshot:
  `11bdf3367e4099f25afbc750836a1a95488af13d09a226f7357c8cbce978fada`;
- result fingerprint:
  `7a207058792a8e35da35d7a4d4ab384b6621a9ca0ad2ada12f4c883ead652315`;
- physical content fingerprint:
  `643a58f441002838092263dcdbfbaeddebc2d9563c36df03b20d3c190548e5f0`;
- company count: 2,449;
- current fresh count: 2,432.

## Production Immutability

The three production databases that Phase 13F.4 would have written were inspected read-only.
Their hashes remained:

| Database | SHA-256 |
| --- | --- |
| `data/fundamentals_provider.db` | `410c55518c053898c7603bfd43db1d20ee9eeeb9b72f566657126562e85ac40d` |
| `data/fundamentals_v4.db` | `cbb63e42676a3fd90f63f94ff2c123e843d7808b4afb273c264fc745c6839f2d` |
| `data/fundamentals_analysis.db` | `3c8db26ae81d2a7d8f3e331fea6bfd3926260c6efc05f7f3b3dece06e967bdea` |

Production active OI V2 remained:

- active package:
  `f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`;
- package economic fingerprint:
  `7448d7b9212ce4645cf000d6264d824f3f488cdf5d7fce3ba7f6df839c3b8e78`;
- package physical fingerprint:
  `369793b4036a1e407f9721ed6a3f5f455ffc3b7e9500c8ba00ecae92b49ab31d`.

No Phase 13F.4.1 database copy rehearsal was started after the architectural blocker was proven,
because the copy-only apply could not satisfy old/new OI package coexistence without a redesign.

## Verification Performed

- Inspected package persistence schema, manifest construction, activation and readers.
- Inspected package apply deletion/replacement behavior.
- Inspected generic dependency and RV dependency schema.
- Inspected RV snapshot persistence and active pointer behavior.
- Verified current git state before documentation changes.
- Verified production database hashes read-only after documentation changes.
- Ran compile checks for inspected fundamentals modules.
- Ran `git diff --check`.
- Parsed retained JSON evidence.

The complete active test suite was not run because Outcome A was prohibited by the architecture
blocker before implementation or copy-only rehearsal. Running the full suite would not change the
coexistence finding.

## Required Redesign Before Production Deployment

Do not retry Phase 13F.4 production deployment from the current persistence architecture.

Before a Phase 13F.4.2 production attempt can be authorized, a separate redesign phase must prove
on copies that:

- OI V2 result rows are selected by package identity or an equivalent immutable generation key;
- old and structural-aware package generations coexist on the same analysis database copy;
- active pointer selection cannot combine a manifest from one generation with rows from another;
- archived readers can open old package semantics when the old manifest is selected;
- structural-aware manifests fail closed when structural dependencies are missing or mismatched;
- RV dependencies reference the selected package generation and structural dependency set;
- pointer rollback is either coherent by package generation or explicitly refused with full-backup
  rollback as the only supported recovery path;
- second identical apply performs zero logical writes and no physical change.

Only after that evidence exists should the production attempt be named Phase 13F.4.2.
