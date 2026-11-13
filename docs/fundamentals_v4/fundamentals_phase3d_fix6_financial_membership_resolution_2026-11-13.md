# Fundamentals Phase 3D FIX6 — financial identity and membership decision

Subsequent [FIX7](fundamentals_phase3d_fix7_approved_financial_selection_2026-11-13.md)
implements the operator's now-explicit twelve financial representative decisions
in a purpose-specific native version contract and disposable candidates. The
investigation below records the prior decision boundary. Production installation
still requires a qualified native reconciliation adapter and separate authorization;
the FIX6 production state is not silently updated by the source implementation.

**Verdict: bounded audit complete; live Refresh remains BLOCKED. No source
correction is justified by the accepted contract.** Existing financial ownership
is proven for all twelve groups. Existing authority does not complete their
incoming Refresh selections. StockCore corroborates issuer/security/provider
relationships and clarifies CYCN/KRSA's price-facing lifecycle; it supplies no
RawCandle membership grant or new Sharadar mapping.

Starting HEAD: `74bd34ea55f22a733fd137b2762207ae62390513` (accepted FIX5).
Governing reports: [FIX5](fundamentals_phase3d_fix5_representatives_actual_history_2026-11-13.md),
[FIX4](fundamentals_phase3d_fix4_identity_retention_2026-11-13.md),
[FIX3](fundamentals_phase3d_fix3_refresh_universe_2026-11-13.md).
This report is the only versioned task change. No production reconciliation,
identity integration, new registry, synchronization or ID allocation occurred.

## Current authority and population

Fresh immutable read-only queries selected active generation
`current_rebuild_2a684ef130c6a540de4adc560ab171ad`, and installed universe
`3b8121b74c852f08575fa1e2b70004e6`, as of `2026-09-20`.

| Installed company-level population | Companies | Recorded active securities | Non-null selected security IDs |
| --- | ---: | ---: | ---: |
| ACTIVE_SINGLE_SECURITY | 2,441 | 2,441 | 2,441 |
| ACTIVE_MULTI_SECURITY | 11 | 22 | 0 |
| HISTORICAL_RETAINED_NO_ACTIVE_SECURITY | 16 | 0 | 16 |
| Total | 2,468 | 2,463 | 2,457 |

There are 2,495 versioned alias rows. The recorded physical securities total
2,480, including seventeen securities under the sixteen historical companies.
Those are installed counts, not a claim that 2,463 securities are currently
eligible for acquisition. The native reader presently rejects the whole binding
with `REFRESH_UNIVERSE_SECURITY_CONTRADICTION` for company 627 before creating a
new UPDATE. No eligible population was manufactured by suppressing that error.

Physical existence, a versioned company member, a selected security, accepted
provider observations, canonical financial provenance and incoming eligibility
are separate facts. A company quarter has no second copy merely because the
issuer has two traded share classes. All twelve companies have one historical
financial-source owner; the other class shares company economics without gaining
ownership of that source's provider ID, price or share context.

## What the native contract actually permits

The [Phase 13B foundation](fundamentals_v4_phase13b_foundation.md) explicitly
defines a **company-level** universe, sets `security_id` only for exactly one
active security, and leaves multi-active companies for later security selection.
`phase13b_foundation.current_universe_rows` implements that distinction;
`universe_identity` binds the status and physical counts into the economic
fingerprint/version. All eleven installed rows explicitly say
`MULTIPLE_ACTIVE_SECURITIES_REQUIRES_SECURITY_SELECTION`, with null selection.

FIX3's `InstalledUniverse` does **not** require duplicate financial acquisition
for every physical share class. It checks installed physical-count/ownership
consistency and requires an authorized incoming security. Both aliases of each
multi-security company are actually installed. Calling the companion a nonmember
because it has zero financial observations would remove unresolved admitted
authority by inference. The user's update-only/nonmember instruction does not
authorize that removal. A unique observed financial source also does not replace
the contract's explicit unresolved selection.

Similarly, disregarding the stale 1/1 counts for CYCN solely because its selected
security still exists would reinterpret the installed economic contract. No
accepted purpose-specific exception permits it. A new policy distinguishing a
financial selector from physical share classes may be a small future change, but
it is a policy/version reconciliation, not an independently proven reader defect.
No ticker-specific exception or broad identity relaxation is introduced here.

## StockCore evidence and its limits

StockCore was located at `/home/kalle/projects/stockcore`; observed clean HEAD
`26e542243f2b71eeb193fe76170bc7a0b688b8b4`.
Reads were limited to the twelve groups in:

- `runtime/osakedata_ng.db`: company/CIK, security payload, accepted routes,
  Sharadar associations and their stored evidence; scoped membership rows.
- `runtime/fundamentals/fundamentals_v4_ng.db`: matching canonical identities,
  exact Sharadar mappings and the existing cutover record.
- `runtime/fundamentals/acceptance.json`: accepted copy binding
  `d253ad70aba63b6f07a61454369ae2dbdd16edb7bbcd39f501434995d0cfb938`, from
  `refresh_20261020T042943Z_refresh_fundamentals_a25cdb749cf4_production_13793465`.

The P01 identity version label remains
`g-data05-five-supported-renames-and-enlv-class-20261107`, fingerprint
`04bb8736e017e127fab21e898975f62c3f159620e11638c59aec0ca382e665b4`.
The observed copied canonical cutover records owner `stockcore` on October 20.
That is an existing StockCore fact, not a new handoff performed here or authority
to overwrite RawCandle IDs/membership. Early P01 documents describing an uncutover
fixture are historical; current stored evidence governs the observation.

For all 24 securities, issuer IDs, company CIKs and Sharadar map IDs match
RawCandle. All eleven pairs have distinct security IDs and matching provider
associations; classification: **MATCHES RAWCANDLE AUTHORITY**. Most are retained
owner projections, not independent fresh external provider verification. Yahoo
routes were inspected separately and never used to infer Sharadar identities.

CYCN/KRSA: **CLARIFIES A RAWCANDLE AMBIGUITY** for succession/lifecycle and
**CONTRADICTS RAWCANDLE** if comparing the price-facing active flag literally.
The discrepancy is explicitly scoped in StockCore's
`docs/g_data_25_identity_and_terminal_changes.md` and accepted G-DATA-25 security
payload evidence: CYCN/628's price segment ends exclusively at `2026-09-09`;
KRSA/2558 starts then, preserving issuer 627. StockCore marks CYCN inactive and
KRSA active; its copied base still has both active, just like RawCandle. The
document says financial files/base rows were unchanged and Fundamentals
membership was not removed. Its terminal price qualification is therefore not
a RawCandle financial retirement instruction.

StockCore retains CYCN's Sharadar association `111101`; KRSA has **none**. Its
accepted Yahoo KRSA route is not a replacement financial map. Neither system
proves that KRSA should borrow CYCN's provider identity.

## Company/security decision matrix

`M` = admitted company row ACTIVE_MULTI_SECURITY, null financial selection;
the security's own alias is present in that installed version.
`S` = installed ACTIVE_SINGLE_SECURITY selecting CYCN/628, with stale 1/1 counts.
Financial counts below are retained ARQ/MRQ observations and canonical quarters
whose field provenance actually names that security. A zero means no **direct**
financial source ownership; company history is still available through its peer.
Analysis score endpoints are company-owned and match the listed quarter counts.

For each multi-security company, disposition **R** means
**OPERATOR_DECISION_REQUIRED**: approve/reject the source-bearing tuple for
financial Refresh only, keep both security identities and OLD, and explicitly
state the companion's incoming treatment. Neither companion is declared a
nonmember. A supported native financial selection/version reconciliation is
required before live eligibility changes; backfill alone retains null selection.
This single action applies to both rows of its company.

| Company / ID | Security / ID | RC identity / membership | Sharadar map | Financial rows / direct canonical quarters | StockCore evidence | Proposed Refresh disposition / approval / mutation |
| --- | --- | --- | --- | --- | --- | --- |
| CENT / 442 | CENT / 442 | Active / M | 197778 | 81 / 41 | MATCHES; same issuer/map | R: source tuple 442/197778; operator + native selection/version |
| CENT / 442 | CENTA / 443 | Active / M | 114230 | 0 / 0; company via CENT | MATCHES; distinct secondary class | R: retain admitted companion; no duplicate statements |
| CYCN / 627 | CYCN / 628 | Active / S | 111101 | 112 / 32 | Lifecycle clarification; P01 inactive | Existing OLD owner RESOLVED_BY_EXISTING_AUTHORITY; incoming OPERATOR_DECISION_REQUIRED (C below) |
| CYCN / 627 | KRSA / 2558 | Active; company admitted; no selected/versioned KRSA alias | None | 70 / 0; company via CYCN | Same issuer/successor; no Sharadar map | Incoming blocked, not newly added; OPERATOR_DECISION_REQUIRED (C) |
| FOX / 886 | FOX / 887 | Active / M | 111122 | 0 / 0; company via FOXA | MATCHES; distinct secondary class | R: retain admitted companion; no duplicate statements |
| FOX / 886 | FOXA / 888 | Active / M | 111125 | 70 / 33 | MATCHES; same issuer/map | R: source tuple 888/111125; operator + native selection/version |
| FWONA / 912 | FWONA / 914 | Active / M | 191707 | 82 / 41 | MATCHES; same issuer/map | R: source tuple 914/191707; operator + native selection/version |
| FWONA / 912 | FWONK / 915 | Active / M | 119287 | 0 / 0; company via FWONA | MATCHES; separate class | R: retain admitted companion; no duplicate statements |
| GOOG / 969 | GOOG / 972 | Active / M | 119496 | 0 / 0; company via GOOGL | MATCHES; separate class | R: retain admitted companion; no duplicate statements |
| GOOG / 969 | GOOGL / 973 | Active / M | 195146 | 82 / 41 | MATCHES; same issuer/map | R: source tuple 973/195146; operator + native selection/version |
| LBTYA / 1272 | LBTYA / 1277 | Active / M | 191556 | 82 / 41 | MATCHES; same issuer/map | R: source tuple 1277/191556; operator + native selection/version |
| LBTYA / 1272 | LBTYK / 1278 | Active / M | 119285 | 0 / 0; company via LBTYA | MATCHES; separate class | R: retain admitted companion; no duplicate statements |
| LILA / 1296 | LILA / 1302 | Active / M | 121104 | 75 / 36 | MATCHES; same issuer/map | R: source tuple 1302/121104; operator + native selection/version |
| LILA / 1296 | LILAK / 1303 | Active / M | 114228 | 0 / 0; company via LILA | MATCHES; separate class | R: retain admitted companion; no duplicate statements |
| LLYVA / 1307 | LLYVA / 1314 | Active / M | 640301 | 18 / 7 | MATCHES; same issuer/map | R: source tuple 1314/640301; operator + native selection/version |
| LLYVA / 1307 | LLYVK / 1315 | Active / M | 640300 | 0 / 0; company via LLYVA | MATCHES; separate class | R: retain admitted companion; no duplicate statements |
| METC / 1407 | METC / 1415 | Active / M | 124161 | 81 / 40 | MATCHES; same issuer/map | R: source tuple 1415/124161; operator + native selection/version |
| METC / 1407 | METCB / 1416 | Active / M | 640161 | 0 / 0; company via METC | MATCHES; distinct secondary class | R: retain admitted companion; no duplicate statements |
| NWS / 1600 | NWS / 1609 | Active / M | 119317 | 0 / 0; company via NWSA | MATCHES; separate class | R: retain admitted companion; no duplicate statements |
| NWS / 1600 | NWSA / 1610 | Active / M | 191637 | 82 / 41 | MATCHES; same issuer/map | R: source tuple 1610/191637; operator + native selection/version |
| UA / 2243 | UA / 2253 | Active / M | 119495 | 0 / 0; company via UAA | MATCHES; separate class | R: retain admitted companion; no duplicate statements |
| UA / 2243 | UAA / 2254 | Active / M | 194726 | 82 / 41 | MATCHES; same issuer/map | R: source tuple 2254/194726; operator + native selection/version |
| Z / 2441 | Z / 2452 | Active / M | 119315 | 0 / 0; company via ZG | MATCHES; separate class | R: retain admitted companion; no duplicate statements |
| Z / 2441 | ZG / 2458 | Active / M | 179220 | 82 / 41 | MATCHES; same issuer/map | R: source tuple 2458/179220; operator + native selection/version |

Evidence strength is direct accepted RawCandle financial provenance plus exact
installed rows/maps, with matching stored StockCore identity evidence. That is
strong financial-ownership evidence and incomplete selection authority. No share
class is preferred by price, volume, capitalization, ticker order or minimum ID.
No representative decision changes price/shares/ownership/P/B semantics here.

### C — exact CYCN/KRSA boundary

Current company 627 has two physical active securities but a member selecting
CYCN with active/all counts 1/1. CYCN is the uniquely mapped financial identity:
native `resolve_identity` returns KNOWN/628/111101. All 32 canonical quarters and
32 score endpoints belong economically to issuer 627 through CYCN provenance.
KRSA has 160 accepted OLD provider observations (70 ARQ/MRQ), with null provider
IDs, but zero canonical field-provenance ownership and no installed KRSA alias.
Native financial identity resolution returns NOT_IN_CANONICAL_UNIVERSE because
its required identity join lacks the provider map; this message does **not** mean
the physical security is absent.

Therefore KRSA is not proven to have independent canonical financial coverage
or incoming Refresh authority. It must not be acquired/added automatically.
It is also not a security with no accepted Fundamentals data: its OLD provider
rows must survive. Company-level admission, separate accepted onboarding and the
stale installed single-security invariant prevent treating its absent alias as
sufficient proof of an ordinary outside-company nonmember. **Proven nonmembers
newly excluded among the twelve groups: none.** Both distinctions matter.

Keeping CYCN as historical financial owner is already authorized retention;
declaring it HISTORICAL_RETENTION_ONLY for incoming Refresh is a different
decision. Keeping CYCN as the current Refresh source while omitting KRSA needs
an explicit financial-purpose resolution of the stale native membership. Retiring
CYCN in RawCandle is not authorized by StockCore's price segment or this task.

Exact pending action C: approve CYCN/628/111101 as the continuing financial-only
source or place issuer 627 into an explicitly reviewed historical/held incoming
state; specify KRSA/2558's incoming nonparticipation while retaining all OLD. If
KRSA is to replace the source, first establish its own verified financial mapping
and authority. Preserve the accepted same-company succession decision and IDs.
Under today's physical-count contract, a new installed version is necessary to
reconcile the stale member; rerunning the current backfill would instead produce
an unresolved multi row, not the requested financial selector.

There is no ready-made native writer that installs the proposed purpose-specific
multi-security choices. A separately authorized bounded contract/selection change
and owned-copy rehearsal are needed before native generation publication. Do not
issue a direct SQL patch, mutate a version in place, copy a provider ID, replay a
completed admission, or pretend the existing backfill is such a selector.

## OLD preservation, validation and production state

All existing OLD provider/canonical/analysis data remains authoritative regardless
of proposed incoming participation. FIX4 PSQL/QVCG proof code and exact active-role
bytes are unchanged from the accepted FIX5 proof (respectively two/forty canonical
quarters, null provider maps). Incoming exclusion never deletes these histories
or grants admission through a historical proof. No financial-review, source-hold,
accounting, publication-date or provenance restriction is relaxed.

Targeted queue reads found no refresh review, source disposition or P/B review
for the 24 target tickers. This is not a clearance for other accounting/review
obligations or any new capture. Financial approvals remain source/OLD/queue-bound.
Fresh native FIX5 historical preflight returns `NO_AT_RISK_ACCEPTED_HISTORY`,
checking all seventeen inactive companies. The analysis bytes match the prior
all-38-table audit; no unsupported importer is required for today's empty inactive
endpoints. Real unsupported history still STOPs and actual loss still invokes
native rollback under the unchanged FIX5 implementation.

Validation executed in FIX6: immutable SQLite reads, 24 issuer/CIK/provider
cross-checks, exact version/population/provenance queries, native read-only identity
resolution, expected native installed-reader STOP, native actual-history preflight,
and file preservation checks. Outgoing sockets were denied and recorded zero
attempts. **No pytest or disposable workflow was run**, as source behavior did
not change. The accepted FIX5 154-test result is prior evidence, not rerun evidence.
No full suite or StockCore tests were run.

Final full SHA-256/size/inode/mtime comparison: **26,870 protected RawCandle
files, zero differences**, between `2026-11-13T19:16:08.964538+00:00` and
`2026-11-13T19:19:54.614318+00:00`. This covers all 26,861 original
UPDATE/FETCH/validation files, three active financial roles, active manifest,
journal, review queue, scheduler and market/taxonomy dependencies. Another 38
admission/registry files match the accepted FIX5 inventory exactly. The three
queried StockCore runtime files above also matched before/after in full SHA-256,
size, inode and mtime; its worktree remains clean at the observed HEAD.

| Unchanged queried StockCore file | Bytes | SHA-256 |
| --- | ---: | --- |
| `runtime/osakedata_ng.db` | 6,220,156,928 | `35080105998df2081547523b3a3b28b5b17cce407d6a397496abd6f0935a6afe` |
| `runtime/fundamentals/fundamentals_v4_ng.db` | 754,466,816 | `d6ab15e3674156dc89d7f511b6c82f2e9a0e75efa69fd22b19cfdd5d76eb468c` |
| `runtime/fundamentals/acceptance.json` | 103,769 | `7ea22d4036912f40c4bbf869c6e262facdef028ba4d9d3c00a83cfade983f400` |

Active generation and universe remain as named above; provider watermark remains
`2026-10-28`. Scheduler configuration remains `FULL_WORKFLOW` / `SNAPSHOT_V1` /
`fundamentals_refresh_preview_enabled=false`: **HOLD YES**. StockCore writes,
RawCandle identity/universe/financial/review writes, active generation/watermark
changes, live/new UPDATE, publication, financial acceptance relaxation and
scheduler changes: **NO**. Sharadar HTTP calls **0**; SEC HTTP calls **0**.
No storage optimization, cleanup or original UPDATE-artifact modification occurred.

Evidence lives only in ignored `temp/fundamentals_phase3d_fix6_20261113/`;
no database copies were made, and no generated evidence is committed.

## One next production-readiness action

Review **one consolidated financial-purpose decision**: C plus the eleven source
tuples in the matrix, explicitly retaining companion/OLD history and security
market contexts. Authorize a bounded native selection-contract/version preparation
and disposable validation under exact current OLD/universe/queue fingerprints.
Only after a reviewable candidate exists, separately authorize its native
production reconciliation. The prior version and complete OLD generation must
remain recoverable through normal journal/backup/full-generation rollback; no
standalone membership-row or active-pointer patch is a recovery plan.

After that reconciliation, recheck the current universe, reviews, OLD and HOLD
before separately authorizing a **new UPDATE**. The original blocked UPDATE,
FETCH/SEC bundle and deadline remain immutable and cannot be reprojected into
new authority. This audit executes no live/new/resumed UPDATE, publication or
scheduler change. StockCore contributes evidence only; there is no migration or
synchronization project in this recommendation.
