# Diagnostic Flags V1 persistence

## Semantics and layout

Persistence version `DIAGNOSTIC_FLAGS_REVISED_HISTORY_V1` stores `CURRENTLY_REVISED_DIAGNOSTIC_FLAGS_HISTORY`. It is revised history, not original PIT history. Economic model `CURRENTLY_REVISED_DIAGNOSTIC_FLAGS_V1` and fingerprint `1d985892734c1401de55d91e06bbb1f295fe247e96bb3acbffcd6272027f26ad` are unchanged from Phase 6B.

Selected layout A contains a package, five compact codebooks, one endpoint row per company/fiscal quarter and exactly seven `WITHOUT ROWID` evaluation rows per endpoint. Evaluation evidence uses 16 nullable REAL slots and a boolean bit mask. `EVIDENCE_FIELDS` and `BOOLEAN_FIELDS` version each slot's flag-specific name. Readers return named evidence. Null remains distinct from observed zero.

Layout fingerprint: `f48e6e7b40071fe536b7846cac17c59d2fed7c0b118c4771813348877d065aba`.

Indexes support company current/history, fiscal cross-sections and flag/status filtering. Missing evaluation rows make an endpoint invalid and are never clear. No JSON, prose, copied Lifecycle/Valuation history, combined score, severity, trigger or view is persisted.

## Alternatives

On 50,585 endpoints and 354,095 outcomes, A used 86,380,544 bytes. Alternative B used 27,066,368 bytes by packing all statuses into the endpoint and storing details only for flagged/exception outcomes. B was rejected because clear-result audit requires source reconstruction and company writes must synchronize packed state and selective details. A remains below the 200 MB blocker and is operationally simpler and fully self-auditing.

## Writer and reader contract

The writer validates all seven outcomes, fingerprints every row, inserts deterministically, replaces one model package or complete selected company histories atomically, preserves unrelated packages, and detects an identical apply before writing. It never uses `INSERT OR REPLACE`. Failure injection covers schema, codebooks, package metadata, deletion, partial/full endpoints, partial/full evaluations and final verification.

The repository supports package metadata, one endpoint, current company, current batch, full company history, fiscal cross-section, current one-flag filter and current flagged universe. Every call requires the explicit economic fingerprint and preserves deterministic flag order.

## Upstream and pipeline

The five working-capital fields must pass their migration/backfill validation before Diagnostic Flags persistence. Production currently lacks normalized provider `netinccmn`, although all provider payloads contain the key and canonical common earnings/TTM outputs are already populated. The existing Phase 3B additive compatibility migration safely adds/backfills the column without changing canonical outputs; it is therefore an explicit Phase 6D prerequisite, not a new economic decision.

The proposed stage runs after committed Valuation, because Score Trajectory, Lifecycle-derived applicability, canonical TTM/common earnings and Valuation are prerequisites. Delta and Relative Position are not prerequisites. Until a reliable complete changed-company set exists, use full-history rebuild. A diagnostic failure is reported independently and does not roll back already committed upstream stages. Phase 6C does not activate this hook.

## Rehearsal result

Production-shaped copies reproduced 50,585 endpoints, 354,095 outcomes and current union 433/2,097 (20.65%). Decision and numeric-evidence mismatches were zero. First persistence apply inserted all rows; the identical second apply made zero logical changes. Production databases were unchanged.

The authoritative rehearsal fingerprints are:

- source: `6c0ef9696386e8c9e47856d5e61ab4456dea4f6b05a6982f7a87c76e87c9dfe3`
- economic result: `e712798c9c4d6dc43d26d1a638e434ba9e97e9d8dcaa43c5c51764c200bc4f51`
- package: `9cb22911df493b71a54985c81eae3de9e5d5ad5db259cbe9fc70b57cb6b49b4d`
- persisted physical content: `e21536fd5b693d20773808ce89bd79f0ca23783067a100e08893861cf0006461`

The first persistence apply took 10.23 seconds after package construction; the second apply returned `NO_CHANGE`. Current-company reads measured 0.016 ms median / 0.018 ms P90, 20-company batch reads 1.33/1.55 ms, deterministic current flagged-universe reads 91.62/93.78 ms and fiscal-quarter audits 49.89/56.50 ms. The prototype's 86,380,544-byte growth is about 1,707 bytes per endpoint, including all seven evaluations and indexes.

The schema objects are `diagnostic_flag_package`, five codebooks, `diagnostic_flag_endpoint` and `diagnostic_flag_evaluation`. Its three indexes are `idx_diagnostic_flag_current`, `idx_diagnostic_flag_cross_section` and `idx_diagnostic_flag_filter`. The package and endpoint tables use ordinary rowids for compact surrogate references; evaluation uses the composite `(endpoint_id, flag_id)` primary key `WITHOUT ROWID`.

## Safety and limitations

The Phase 6C CLI is dry-run by default, requires absolute explicit paths, an explicit scope and the locked economic fingerprint, and has no production-confirmation option. It blocks production paths, symlinks, the repository data directory, source-as-destination, and provider/canonical/market/taxonomy schemas as diagnostic destinations. It performs no provider update and creates no pipeline hook.

The current implementation intentionally rebuilds the full source package before a company-scoped write, and the proposed pipeline falls back to full-history refresh until a reliable complete changed-company set exists. Cross-database atomicity is not claimed: the Phase 6D runbook uses verified backups and validation gates. Persisted data remains currently revised history and cannot answer original point-in-time questions.

Production integrity after rehearsal was clean for all five identified databases. Main-file SHA-256 values were provider `17660df9f00837fbb52668aff17144d1b167aae4458dfa1a3c057701924b6d9c`, canonical `2e4bc3d99c1eca1d1b28eaacffe581fad61f6a2ef7ead7dee2eeae1a0338ee10`, analysis `55b22d0fa0357aff6b85d21fd5fac7af8961d7c46bc03d644487e02c5483d456`, market `42b661d17f953e9bc592701e9e98df9876e44ed0ce40d0f54d2c8ee0e6126344`, and taxonomy `538cc96d1b55ceb1d7283f426c6cb1ab3bfd1f81206ccbe4bcd9b7dbd3b46ae2`. Sizes and mtimes matched preflight, all read-only `quick_check` results were `ok`, and all foreign-key checks returned zero rows. Taxonomy `analysis.db` retained its pre-existing zero-byte WAL and 32 KiB SHM sidecars; they were not created, deleted or modified as production data by Phase 6C.
