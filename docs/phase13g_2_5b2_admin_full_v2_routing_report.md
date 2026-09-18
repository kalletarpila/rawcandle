# Phase 13G.2.5B2: Fundamentals Administration full V2 routing

## Dependency decision

| Administration change | Downstream action |
| --- | --- |
| Add Tickers | Fresh full V2 analysis rebuild, including RP V2 and RV |
| Sector/Industry | Fresh full V2 analysis rebuild, including RP V2 and RV |
| Taxonomy | Fresh full V2 analysis rebuild, including RP V2 and RV |
| Repair or uncertain state | Fresh full V2 analysis rebuild, including RP V2 and RV |

There is no RP-only or Sector/Industry-only publication path. The shared
`run_full_v2_downstream` adapter calls the B1 `rebuild_v2_analysis` entrypoint
once with copied provider, canonical, market, and taxonomy authorities. It
never supplies the old analysis DB as a calculation source. B1 validates its
fresh V2 package, active RP V2, RV, taxonomy dependency, readers, SQLite
integrity, and foreign keys before reporting `READY`.

## Taxonomy ownership

The separate taxonomy program owns CSV reading, validation, writing, and
activation. Fundamentals Administration neither accepts a taxonomy CSV in its
active UI/CLI route nor writes or activates taxonomy data. Its Taxonomy action
reads the currently active `dc_ecosystem` domain from `data/analysis.db` (or
its production-shaped copy) and rebuilds Fundamentals from that state. The
rebuild result records the exact active version and semantic fingerprint read
by B1. A saved preview binds the source state and as-of date; a changed source
requires a new preview. All three Admin copy-update summaries expose that B1
taxonomy identity, not a submitted CSV version.

## Copy-only acceptance

On 2026-09-18, a read-only production-source Taxonomy preview and one
`Test on copies` run completed. The copy run built a fresh candidate and
reported `FULL_V2_REBUILD` with one package, RP V2, and RV invocation. B1
validation reported 87,860 Score rows, 87,860 Valuation rows, 13,799 RP V2
result rows, and 2,444 RV inputs. The package had no duplicates or orphan
rows, `quick_check=ok`, and no foreign-key violations. The active taxonomy
was `DC_TAXONOMY_FULL_V2_1`, semantic fingerprint
`801698f6b352c445cc8e6f5fd51a1cac2779d11f6ce72a1c10bf71bb8aae4559`.
The same identity appeared in preview and validated rebuild.

Thirty-two taxonomy tickers remain unmapped to a unique canonical company;
this phase does not repair identities. After the rehearsal, the source-state
fingerprints and active taxonomy matched the preflight preview exactly.
Disposable database copies and the candidate were removed; the run reports
remain under `/tmp/rawcandle-b2-taxonomy-preview` and
`/tmp/rawcandle-b2-taxonomy-copy`.

A separate production-shaped, copy-only Add Tickers rehearsal used `GFS`,
which the read-only preview marked `ELIGIBLE`. The first copy apply was
`APPLIED`; its single full V2 rebuild validated 87,882 Score and Valuation
rows, 13,807 RP V2 result rows, and 2,444 RV inputs. The repeat apply was
`NO_CHANGE` with zero downstream invocations. In the copy, the active
Datacenter taxonomy retained the same version and semantic fingerprint but
mapped GFS to a canonical company, reducing unmapped taxonomy tickers from
32 to 31. Production remained at 32. A GFS Snapshot smoke report was created
without exposing internal IDs. Its original rehearsal used the older fixed
smoke report date; the code now binds smoke to the saved preview as-of date,
with a focused regression test. After the run, the production source state,
analysis DB fingerprint, and active RV identity matched their preflight
values. All phase-owned DB copies were removed. Evidence remains under
`/tmp/rawcandle-b2-add-preview` and `/tmp/rawcandle-b2-add-copy`.

A Sector/Industry changed-state rehearsal used a separate production-shaped
source copy. Only that copied `ticker_meta` changed NVDA from
Technology/Semiconductors to Financial Services/Banks - Diversified. The
preview identified one correctable ticker and 62 affected source rows. The
copy apply changed those rows, performed exactly one fresh full V2 rebuild
and RV calculation, passed B1 validation, and returned `NO_CHANGE` on repeat
with zero downstream invocations. Relative Position produced 13,795 rows;
RV used 2,444 inputs. With the same as-of date and otherwise unchanged
sources as the active-taxonomy rehearsal, Score's semantic fingerprint stayed
`80225e0a027e48b6a527d14e3322e1b102d759e7ad9f16054ef2ce56ab93ece6`,
while Valuation changed from `6d33ecb8b94340b962ae93788f65f134fc8732e37c223ecfb7fa9767c6c353e1`
to `8eba84a6e7ec384ee6f90f3afab2357efeff891255e94f8b08602399d0453db6`
and Diagnostics changed from `b698f891eda9095f6600965982564aa64908a7dcedb1bdc4788d37c73e2e50a6`
to `1d6d3d4ba89c1e376e1444461fbc320c75749feaaabcf0a7d8dcf756bc20ddd5`.
The candidate's NVDA Valuation rows were `NOT_APPLICABLE` with
`UNSUPPORTED_BANK_MODEL`; production still showed NVDA as
Technology/Semiconductors. This directly rules out the earlier RP-only
Sector/Industry plan. All phase-owned source and apply DB copies were
removed; reports remain under `/tmp/rawcandle-b2-sector-fixture`.

## Production boundary

No production Admin update, source DB write, analysis replacement, or
production RV run was performed in B2. The Add Tickers and Taxonomy
`Production update` entrypoints fail closed pending an atomic full-V2
replacement contract. The Sector/Industry production CLI remains limited to
its existing no-change verifier; its UI write action is disabled. A later
phase must implement preview-bound atomic analysis replacement, rollback,
scheduler coordination, and postflight checks before any changed-state
production update is authorized. Legacy RP V1 code outside active Admin
routing remains for the separate retirement phase.
