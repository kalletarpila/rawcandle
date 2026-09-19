# Phase 13G.3.3 Refresh Copy Test and Rebuild

## 1. Outcome

Phase 13G.3.3 succeeded. Refresh Fundamentals now supports Preview and Test on
copies. Production update and scheduler execution remain unavailable.

The accepted live Test run was
`20260919T195732Z_refresh_fundamentals_0470057ce75c_test`, bound to Preview
`20260919T195229Z_refresh_fundamentals_0fb542ea4f44` and refresh-set fingerprint
`601755ff823d8e70da33b5b684cd0757e031b5cc62c85c9e68d42b299fdd7d39`.

## 2. Preview/Test Binding

Test requires a successful, complete, non-NO_CHANGE Preview with zero blocking
review cases, schema evidence, a deterministic refresh-set fingerprint, and at
least one effective changed known ticker. It re-runs discovery and complete ARQ
and MRQ acquisition before creating any candidate path. Any schema, baseline,
watermark, ticker-set, classification, or normalized source fingerprint change
fails as `STALE_REFRESH_PREVIEW`. The stale regression proves no phase-owned
provider, canonical, or analysis candidate exists after rejection.

## 3. Legacy True-Key Tie Diagnostic

Production read-only diagnostic:

- repeated true-key groups: 835;
- unique maximum `lastupdated`: 835;
- same-maximum identical content: 0;
- same-maximum conflicting content: 0;
- affected ambiguous tickers: 0.

Current-state reads now reject same-maximum conflicting effective content as
`LEGACY_SOURCE_VERSION_AMBIGUITY`; they never use observation order as a tie
breaker. Unique maxima and same-maximum identical rows collapse deterministically.

## 4. Provider Replacement

Each of the 70 effective changed known tickers received complete ARQ and MRQ
replacement on the provider candidate. The live selected-ticker totals were ARQ
2554 to 2532 and MRQ 2610 to 2575. Candidate histories matched source row counts,
true-key sets, effective fingerprints, and raw fingerprints exactly.

## 5. True Source-Key Storage

Refreshed rows use `(ticker, dimension, date, reportperiod)` as
`provider_record_key`. The candidate contains one current row per true source key
for refreshed ARQ/MRQ histories. Untouched legacy rows were not migrated.

## 6. Deletion Safety

Deletion authority requires complete, nonempty, nontruncated, structurally valid
ARQ and MRQ responses. Provider parent rows are deleted under foreign keys and
their native children cascade. Candidate checks reported `quick_check=ok`, zero
FK errors, zero orphan children, and unchanged unrelated provider state.

## 7. Publication-Date Bootstrap

The pre-refresh production pair was re-audited before candidate reconstruction:

- canonical quarters inspected: 88,835;
- bootstrap eligible: 88,835;
- repair required: 0;
- bootstrapped in candidate: 88,835;
- preservation map applied: 88,787 / 88,787 surviving existing quarters;
- new-quarter dates established: 56;
- removed-quarter dates retained in evidence: 48.

## 8. Two-Field Date Contract

`source_availability_date` follows the current winning Sharadar row and may
change. `first_public_result_date` is keyed by stable
`(company_id, fiscal_year, fiscal_quarter)` and cannot change in routine refresh.
Targeted regression separately proves that source availability may move while an
established first-public date remains fixed. Publish-date repair remains a
separate future operation.

## 9. Fresh Canonical Rebuild

Canonical identity/control state and derived financial state are separate
contracts. The candidate preserves company, security, aliases, and provider
identity mappings, clears only derived quarter, financial, provenance, TTM, and
structural state, then reconstructs those tables from provider ARQ winners.

Explicit invariant:

`company/security identity mapping before candidate rebuild == after candidate rebuild`

Result: true. Both sides contained 2,505 companies and 2,517 securities with
fingerprint `591cec4342423f0f80837d68ab579d124483def3cc1a935e8d9e81b06bc23a57`.

Explicit invariant:

`first_public_result_date preservation map applied: 88787/88787 existing quarters`

## 10. Canonical Impact

The candidate contained 56 added, 185 changed, and 48 removed quarters. There
were 17 source-availability-date changes, 88,602 bootstrap-only date changes,
and zero unexplained changes outside affected companies. Removed quarters were
not retained as stale rows.

## 11. ARQ/MRQ Semantics

Canonical financial values remain ARQ-based. MRQ is retained in the provider
candidate and does not overlay ARQ fields. `MRQ overlay intentionally deferred.`

## 12. Full V2/RP/RV Rebuild

The existing shared full rebuild ran exactly once and returned READY for V2,
RP V2, Relative Coverage, and RV. Active taxonomy was read from production-shaped
`analysis.db` copies: domain `dc_ecosystem`, version
`DC_TAXONOMY_FULL_V2_1`, semantic fingerprint
`801698f6b352c445cc8e6f5fd51a1cac2779d11f6ce72a1c10bf71bb8aae4559`.

## 13. Analytical Impact

Among the 70 changed tickers, latest-output comparisons changed Score for 62,
Valuation for 41, RV for 41, Lifecycle for 5, and RP result count for 3. A source
revision did not automatically imply a changed model result.

## 14. Representative Tickers

- AI, `NEW_QUARTER`: source latest 2026 Q4 to 2027 Q1; Score NOT_READY to FULL,
  value null to 6.2761.
- GOSS, `HISTORICAL_REVISION`: 68 source rows changed; Score LIMITED 5.0 to
  FULL 46.5707.
- ABAT, `NEW_QUARTER_AND_REVISION`: 2 added, 9 changed, 1 removed; Score
  LIMITED 5.0 to FULL 47.3324.
- ABM, `SOURCE_REMOVAL`: 2 rows removed; canonical removal was deterministic,
  while current Score, Lifecycle, Valuation, RP count, and RV stayed unchanged.

## 15. Test UX

The report has an executive summary, publication bootstrap section, explicit
invariants, and a concise per-ticker source/canonical/Score table. Rich before and
after evidence remains in JSON artifacts rather than overloading the report.

## 16. UI State

Refresh Fundamentals exposes Preview and Test on copies. Test is enabled only by
an authorized changing Preview and is disabled for NO_CHANGE, review/incomplete,
running, and completed-Test states. Production update and full workflow remain
unavailable. The next-step text states that Production is not yet enabled.

## 17. Future Trigger Architecture

Manual UI and a future scheduler will call this same backend workflow and its
discovery, source validation, replacement, rebuild, and guard contracts. No
scheduler-specific path was added.

## 18. Runtime and Storage

Accepted live Preview completed in about 53 seconds. Accepted live Test completed
in 505 seconds. It used one provider candidate, one canonical candidate, one
fresh analysis candidate, and stable market/taxonomy copies.

## 19. Production Safety

Provider, canonical, analysis, market, and taxonomy database size and nanosecond
mtime snapshots were equal before and after the accepted Test. Production writes
were zero. Production refresh state and `first_public_result_date` were unchanged.

## 20. Cleanup

The accepted run removed its complete phase-owned temporary lane after retaining
lightweight reports and JSON evidence. Failed live attempts also removed candidate
lanes. No production rollback backup was touched.

## 21. Tests

- Focused Refresh/provider suite: 50 passed in 7.46 s.
- Focused Refresh copy/Preview rerun after publish-date correction: 25 passed in 7.25 s.
- Final Refresh/UI focused suite: 74 passed in 10.24 s.
- Final broad Admin, UI, Add Tickers, transaction, workflow, B1/full-V2 suite:
  192 passed in 145.67 s.
- Real network acceptance: fresh Preview then one successful copy-only Test.

## 22. Remaining Issues

Production publication and durable refresh watermark advancement are intentionally
not implemented. A failed first live invocation exposed and fixed the default
client constructor before candidate creation. A later failed copy attempt exposed
and fixed candidate-vs-pre-refresh publish-date audit semantics; all its candidates
were cleaned and production remained unchanged.

## 23. Next Phase

Phase 13G.3.4 must build all three candidates before a publication boundary,
implement a durable multi-file journal, verified backups, source recheck, fsync,
crash recovery, whole-set rollback, postflight, and watermark advancement only
after durable success.

## 24. Git

Intended commit message: `feat: add copy-only fundamentals refresh rebuild`.
The final commit hash is recorded in the completion response.
