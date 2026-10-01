# Phase 13G.3.55: Proven-Local Fiscal-Revision Quarantine

Date: 2026-10-01

Design authority: `fundamentals_v4_phase13g3_54_trug_fiscal_identity_locality_audit.md`

## Outcome

Refresh now classifies the narrowly proven MRQ-only fiscal-revision shape as `TICKER_LOCAL_REVIEW`. TRUG-shaped evidence enters the persistent Review Queue, the ticker's published provider and ARQ-backed canonical state remains authoritative, and safe changes can continue through Test and Production.

Fiscal-identity revisions remain review-required. This phase changes only review scope when ticker-locality is positively proven; it does not accept or publish the revised fiscal history.

All unsupported, incomplete, ambiguous, or conflicting fiscal-revision shapes remain `GLOBAL_BLOCKING_REVIEW`.

## Previous behavior

`classify_review_scope()` previously proved only the oldest-prefix `AMBIGUOUS_SOURCE_REMOVAL` shape. Every other review reason defaulted to global, so `REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION` stopped the entire workflow even when all effects were confined to one MRQ ticker. Phase 13G.3.54 demonstrated that this was a conservative implementation limitation for TRUG, not a shared publication invariant.

## Proven-local criteria

The new fiscal branch is separate from the existing source-window branch. It requires all of the following:

1. Classification remains `REVIEW_REQUIRED` with reason `REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION`.
2. Identity resolution is `KNOWN` and supplies one ticker, company ID, security ID, company key, current ticker, Sharadar provider security/permaticker ID, and provider ticker.
3. All events belong to the reviewed ticker and every event is `FISCAL_IDENTITY_REVISION`.
4. ARQ and MRQ complete-history responses both have `COMPLETE` status.
5. Every revision is MRQ-only and carries the expected review status.
6. Old and current rows have the same exact provider source identity `(ticker, dimension, date, reportperiod)`.
7. Old and current fiscal identities are present, valid, and different.
8. Old and current source fingerprints are present.
9. For each affected report period, published and newly fetched ARQ companion rows exist and both expose exactly the proposed MRQ fiscal identity.
10. Every persisted ARQ companion source key belongs to the same ticker and report period, and every companion key has a durable source fingerprint.

An in-ticker duplicate target fiscal identity remains review-required but does not by itself make the case global.

## MRQ and ARQ companion contract

The comparator now emits explicit evidence on each fiscal-revision event:

- `old_source_identity` and `current_source_identity`;
- `stable_source_key`;
- `old_fiscal_identity` and `current_fiscal_identity`;
- old and current source fingerprints;
- `arq_companion_identity_proof` with report period, proposed MRQ identity, published/source ARQ identities, exact ARQ source keys, and their fingerprints.

The companion proof is `AGREES` only when both published and current-source ARQ contain the report period and each side has exactly the proposed identity. Multiple ARQ filing keys for one report period are allowed only when their fiscal identity agrees.

ARQ fiscal revision, missing ARQ evidence, an ARQ identity conflict, or a non-MRQ revision keeps the item global.

## Fail-closed cases

The branch returns `GLOBAL_BLOCKING_REVIEW` for:

- incomplete ARQ or MRQ history;
- unknown or ambiguous canonical identity;
- missing company, security, company-key, provider-security, or provider-ticker binding;
- cross-ticker event or companion source key;
- mixed fiscal and unrelated source-history events;
- ARQ fiscal revisions;
- unstable or missing old/current source keys;
- missing/invalid old or current fiscal identities;
- missing source fingerprints;
- absent, malformed, or conflicting ARQ companion evidence;
- any other fiscal-revision shape not positively recognized.

The oldest-prefix source-window locality predicate and `ACCEPT_RETAINED_HISTORY` eligibility rules are unchanged.

## Review Queue evidence

For a local fiscal review, `affected_source_keys_json` stores every exact MRQ source key. `fiscal_identities_json` now stores one durable record per event containing:

- ticker and dimension;
- source, old-source, and current-source identity;
- old and current fiscal identity;
- old and current source fingerprint;
- complete ARQ companion identity proof.

The existing queue row supplies the queue item ID, review type/reasons, first/last seen timestamps and run IDs, publication binding, status, and review context. The identity context now also preserves company key, current ticker, provider security ID, and provider ticker.

Newly inserted or updated rows include `queue_evidence_fingerprint` in the review context. It authenticates the queue item ID, review classification, reason codes, affected source keys, fiscal evidence, source-evidence fingerprint, publication binding, identity binding, and locality proof. A mismatch raises `REFRESH_REVIEW_QUEUE_EVIDENCE_TAMPERED`. Existing legacy queue rows without this new field remain readable and receive it on their next update.

Fiscal items remain visible and unresolved. Generic `WAIT_FOR_PROVIDER` and `RETRY_REEVALUATION` remain available. `ACCEPT_RETAINED_HISTORY` is not semantically applicable and remains ineligible because fiscal reason codes do not satisfy its unchanged source-window contract. No fiscal acceptance action was added.

## Quarantine and revalidation

`partition_changes()` puts only a positively proven fiscal item in `held`; it never enters the safe replacement set. Candidate construction therefore applies only safe histories. The canonical candidate consumes the resulting provider candidate, which still contains the held ticker's published provider history. This prevents a new-provider/old-canonical mixture for the held ticker.

The full V2/RP/RV rebuild remains valid from that preserved canonical generation. Other companies' cross-sectional outputs may move as safe peers change; this is expected and does not make the held ticker global.

Preview's source-evidence fingerprint now covers the source keys, both fiscal identities, source fingerprints, ARQ companion proof, completeness, and identity. The partition fingerprint includes that evidence fingerprint. Test re-fetches and reclassifies held tickers, then compares the complete refresh-set and partition fingerprints. Any source, companion, identity, or locality drift fails closed as a stale Preview. Production remains bound to the accepted Preview/Test artifacts through the existing production authorization contract.

## TRUG behavior

A targeted read-only validation against the current production baseline and current Sharadar ARQ/MRQ histories produced:

- classification: `REVIEW_REQUIRED`;
- review reason: `REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION`;
- revisions: 8, all MRQ;
- exact affected source keys: 8;
- durable fiscal evidence records: 8;
- ARQ companions agree: true;
- scope: `TICKER_LOCAL_REVIEW`;
- held tickers: TRUG;
- global blockers: 0;
- safe ticker partition: the same 18 tickers established by Phase 13G.3.54.

The validation performed two read-only provider history requests and did not run Preview, Test, Production, or any queue write.

## Tests

Focused coverage adds:

- comparator generation of stable old/current source bindings and ARQ companion proof;
- positive TRUG-shaped MRQ-only locality;
- durable queue storage of old/current identities and companion evidence;
- fiscal items remaining ineligible for retained-history acceptance;
- ARQ revision, ARQ disagreement, incomplete ARQ, incomplete MRQ, identity ambiguity, missing provider identity, cross-ticker evidence, missing fiscal identity, unstable source key, and unrelated event fail-closed cases;
- source/partition evidence drift;
- queue evidence tamper detection;
- a full workflow fixture proving TRUG held, two safe tickers published, provider/canonical preservation, queue visibility, and one successful full V2/package/RP/RV rebuild;
- unchanged YYAI source-window quarantine and global-blocker workflow behavior.

The complete targeted Refresh preview/review/copy/production group passed: `158 passed in 42.57s`.

## Safety

- Production provider database changed: NO.
- Production canonical database changed: NO.
- Production analysis database changed: NO.
- Operational Review Queue changed: NO.
- Live workflow executed: NO.
- Scheduler/systemd state changed: NO.
- Watermark changed: NO.
- TRUG resolved or approved: NO.
- Backups deleted: NO.
- Runtime candidates created in the repository: NO.
