# Phase 13G.3.17 Provider-to-Canonical CIK Synchronization

## Outcome

Phase 13G.3.17 adds a reusable Fundamentals Administration operation for synchronizing authoritative Sharadar CIK values into canonical company identity data. It also fixes Add Tickers so future identities use the canonical ten-digit CIK representation and fail closed on an existing provider-identity conflict.

No live Preview, Test on copies, Production update, Add Tickers, or Refresh workflow was run during implementation. The live databases were read only.

## Fresh Production Audit

The read-only audit on 2026-09-21 produced:

| Measure | Count |
| --- | ---: |
| Canonical companies | 2,545 |
| Canonical companies with CIK | 2,524 |
| Canonical companies without CIK | 21 |
| Active securities | 2,539 |
| Active securities whose company has CIK | 2,523 |
| Active securities whose company lacks CIK | 16 |
| Provider identities linked to active securities | 2,539 |
| Linked provider identities with extractable CIK | 2,526 |
| Linked provider identities without extractable CIK | 13 |
| Missing-CIK backfill candidates | 16 |
| Formatting-only normalization candidates | 86 |
| Already in sync | 2,424 |
| Provider-CIK-unavailable among active canonical missing-CIK companies | 0 |
| Review/conflict cases | 0 |

All historical 16 cases remain present and are `SYNC_ELIGIBLE`: `DMRC`, `FC`, `FUBO`, `GBX`, `HUBG`, `LITS`, `MAGN`, `MCFT`, `NEUP`, `NTNX`, `PFGC`, `SNDK`, `SR`, `UNF`, `XOM`, and `XPRO`.

The 40 later Add Tickers additions did not create another active missing-CIK case. They did expose the old parser defect: 86 existing canonical identities contain an unpadded but numerically correct CIK.

## Provider Contract

The provider currently contains 20,949 `stocks` metadata rows, of which 20,848 have an extractable CIK. There are 6,317 active `stocks` rows, of which 6,307 have an extractable CIK. All 17,828 `fundamentals` metadata rows have an extractable CIK.

Observed non-empty values use one form:

`https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=<digits>`

`provider_cik.extract_sharadar_cik()` accepts only this HTTPS SEC host/path/action contract. It returns an explicit `AVAILABLE`, `UNAVAILABLE`, `INVALID`, or `UNSUPPORTED` state and normalizes a valid value to ten digits. It does not use a permissive arbitrary-URL regular expression and never accesses the network.

Provider-side missing CIK values are accepted source limitations and are not enriched by RawCandle in this phase.

## Canonical Identity Contract

CIK remains company-level identity data. Synchronization follows the existing persistent mapping:

`Sharadar permaticker -> provider_security_identity -> security -> company -> company_cik`

Ticker text is reporting evidence, not the persistent identity join. A missing canonical CIK plus one unambiguous provider CIK is backfilled. Matching values are no-ops. Differing values, multiple CIKs for one company, or one CIK mapping to multiple companies remain review-required and are never overwritten.

The 86 formatting-only cases were proven to have the same numeric CIK, the same company mapping, no normalized key collisions, and a one-to-one matching representation in:

- `company_cik.cik_normalized`, `cik_display`, and CIK-derived `source_value`;
- `provider_company_identity.provider_identifier_value` and its CIK-derived `source_value`;
- `company.company_key` when it is an `SEC_CIK:` key.

They are classified separately as `FORMAT_NORMALIZATION_ELIGIBLE`. The copy/Production mutation updates those linked representations in one canonical transaction. Semantic company and provider-identity fingerprints must remain unchanged. A genuine numeric disagreement remains a conflict and cannot be converted into a formatting match.

## Administration Workflow

`Synchronize provider CIK` is available in Fundamentals Admin with the standard stages:

- Preview is read-only and reports every backfill, formatting normalization, unavailable source, and conflict case.
- Test on copies creates only an isolated canonical copy, applies the exact Preview-bound change set, validates it, records evidence, and deletes the copy.
- Production update requires the exact successful Test, the shared writer lock and journal guard, a freshly validated canonical candidate, and one verified rollback backup. Publication uses atomic replacement plus file/directory fsync and postflight validation.

The write set is canonical only. Provider, market, taxonomy, and analysis remain read-only. Analysis contains no CIK-derived semantic output that requires a V2/RP/RV rebuild.

Candidate validation proves that security mappings, aliases, active membership, quarters, quarter financials, first-public dates, and every non-identity-format canonical table are unchanged. Formatting normalization additionally proves semantic equality of the before/after company and provider-company identity maps. A post-publication fault-injection test proves that the verified backup is restored, its published SHA is verified, the complete pre-publication canonical semantic fingerprint is restored, and terminal `ROLLED_BACK` evidence is written.

## Add Tickers Prevention

Add Tickers now uses the shared parser. A new company with an available provider CIK writes the same ten-digit value to `company_cik`, `provider_company_identity`, and its `SEC_CIK:` company key. Existing unpadded and padded values compare by normalized semantics. An identity already bound elsewhere produces structured `CIK_IDENTITY_CONFLICT` review evidence. Provider CIK absence does not add a blocker and does not alter existing financial, taxonomy, RP/RV, exchange, history, or batch-size rules.

## Files Changed

- `rawcandle/fundamentals/admin/provider_cik.py`
- `rawcandle/fundamentals/admin/cik_sync.py`
- `rawcandle/fundamentals/admin/batch_add_tickers.py`
- `rawcandle/fundamentals/admin/contracts.py`
- `rawcandle/fundamentals/admin/ticker_reporting.py`
- `rawcandle/fundamentals/admin/ui_service.py`
- `rawcandle/fundamentals/admin/operation_report.py`
- `dev_tools/fundamentals_admin_page.py`
- focused backend, Add Tickers, and UI tests

## Database Integrity Evidence

Before and after implementation:

| Role | SHA-256 | Size (bytes) | mtime |
| --- | --- | ---: | --- |
| Provider | `a51320a9492ea915e8acf7bebf75ea76751820ae1911c37e1bb272e6b4acc5fb` | 966,672,384 | 2026-09-20 22:27:31.943840294 +0300 |
| Canonical | `d82f3814c7ddb17eae765b18c4016412fec73f862fd7ae3c2bfd5bde4e3baeaa` | 663,228,416 | 2026-09-20 22:27:55.780235751 +0300 |
| Analysis | `5538fe8dc7be51213c884f43c851f8a7a03594801960f0b336b5a57b7ac0c579` | 913,252,352 | 2026-09-20 22:32:40.159079819 +0300 |

Production DBs changed: **NO**.

Live workflow executed: **NO**.

## Verification And Cleanup

Focused results at report creation:

- CIK synchronization and Admin UI: 50 passed.
- Add Tickers backend: 32 passed.
- Full Workflow, shared Production transaction, and Refresh publication/recovery: 84 passed.
- Total focused/relevant tests: 166 passed.
- Python compilation and `git diff --check`: passed.

Fixture candidate databases and rollback backups were under pytest temporary directories and were removed by fixture cleanup. Repository phase-owned CIK candidate/temp/backup databases remaining: **0**.

The scheduler service and timer were both `inactive`; no Python scheduler/Admin process was running. Scheduler state was not changed.

## Remaining Scope

The operator must still execute and review the live `Preview -> Test on copies -> Production update` sequence. The implementation phase did not apply the 16 backfills or 86 formatting normalizations.

Ticker Transition / Identity Resolution V1 remains a separate next phase. `DRK`, `KRSA`, `PSQL`, and `QVCG` have no ticker-specific logic here.
