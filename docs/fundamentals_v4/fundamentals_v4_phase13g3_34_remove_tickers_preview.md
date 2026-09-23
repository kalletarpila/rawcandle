# Phase 13G.3.34: Remove Tickers Preview

## Contract

`REMOVE_TICKERS` is a read-only Fundamentals Administration operation. It accepts one to 25 ticker symbols and creates a deterministic plan. Test and Production mutation are deliberately unavailable in this phase.

Remove Tickers removes a security from the active Fundamentals universe; it does not blindly delete permanent company/security identity or historical ticker evidence.

The active operational-universe version and `security.active` form an integrity contract with distinct roles. Operational-universe membership defines the managed Fundamentals population. `security.active` identifies securities eligible for current-state readers and downstream participation. A disagreement blocks removal planning; Preview does not guess which state is correct.

## Preserved Identity

Future mutation must preserve permanent `company` and `security` identities, ticker aliases and history, reviewed identity resolutions, historical provider evidence, and unrelated securities of the same company. A historical alias never authorizes removal of its current successor.

For a company with one active security, the planned state deactivates that security and omits the company from the next active operational universe while retaining its permanent identity. For a company with other active securities, only the target security leaves active participation; the company and related securities remain. Canonical financial and analysis outputs are derived state and will be reconstructed in a later phase through the single full V2 + RP V2 + RV rebuild path.

## Classifications

- `REMOVABLE_ACTIVE_SECURITY`: one current active security is consistently present in the active universe.
- `SHARED_COMPANY_PRESERVE_COMPANY`: the target can leave active participation while another active security preserves the company.
- `ALREADY_ABSENT`: the exact current security is inactive and absent from the active universe, or no canonical/provider identity evidence exists.
- `AMBIGUOUS_IDENTITY_REVIEW_REQUIRED`: the request resolves only through historical alias or conflicting incomplete evidence.
- `REMOVAL_BLOCKED`: current identity is non-unique, active-state authorities disagree, membership is inconsistent, or another safety invariant fails.

## Durable Binding

The Preview fingerprint binds the normalized ticker set, resolved company/security IDs, complete current operational-universe fingerprint, relevant provider and analysis fingerprints, classification, expected mutation set, source-contract version, compact-market semantic binding, and active taxonomy version/fingerprint. A later Test must reproduce this material state and reject a stale Preview before creating candidates.

## Read Policy

Provider, canonical, and analysis databases are opened read-only. Market evidence uses `STABLE_SOURCE_BUNDLE`; taxonomy uses `DIRECT_LOCKED_READ` under the authoritative taxonomy lock. Preview creates no full `osakedata.db` or `analysis.db` copy and removes its compact temporary bundle before returning. An active nonterminal publication/recovery journal blocks Preview before source preparation.

## Next Phases

A later copy-only phase must implement candidate mutation, identity invariants, stale-plan rejection, full downstream rebuild, and cleanup. A separate Production phase must add guarded atomic publication and recovery. Neither capability is exposed by this phase.
