# GE / RTX / T — Approved ownership publication and Current P/B release

2026-10-28, Europe/Helsinki. Governing [ownership approval/revalidation](pb_ownership_revalidation_ge_rtx_t_2026-10-28.md), approval commit `2aec0f25fdb7484feccd06478f17e69de539a81b`; [controlled ownership publication contract](fundamentals_v4_pb_ownership_publication_workflow.md), [quarterly ownership contract](fundamentals_v4_pb_quarterly_ownership_durability_v2.md), [new-quarter review workflow](fundamentals_v4_pb_new_quarter_review_workflow.md), and [completed source repair](pb_payload_repair_controlled_workflow_2026-10-28.md).

**Publication COMPLETED; postflight PASSED; recovery NOT_REQUIRED. Exactly GE, RTX and T are PUBLISHED. Their live Current P/B is now OK: 17.55436232103115 / 3.7920742076120066 / 1.3211122199455392.** No new ownership approval, unrelated ownership publication, provider-history change, source-repair decision change, WFRD change, policy/resolver change, auto-continuation or backup cleanup occurred.

Starting HEAD `2aec0f25fdb7484feccd06478f17e69de539a81b`. Fresh baseline recorded **2026-10-28T21:22:19.907553+02:00**; final verification **2026-10-28T21:23:56.437813+02:00**, Europe/Helsinki. Native UTC timestamps remain retained in machine evidence. Existing unrelated worktree/runtime changes were preserved and excluded from the documentation commit. The task itself explicitly authorized this selected publication; no earlier source-repair authorization was reinterpreted as ownership or publication authority.

## 1. Fresh operational preflight and OLD baseline

Read-open, nonblocking preflight verified available scheduler, Fundamentals UI-operation and Production locks; no active scheduler/conflicting operation; safe taxonomy; terminal COMPLETED/PASSED journal with NOT_REQUIRED recovery; clean generation resolution; and no visible/hidden `.preparing` generation. No lock was bypassed or waited on. Normal Admin UI exclusion then surrounded the existing publication workflow, which independently took Production/scheduler followed by taxonomy locks at preview and publication boundaries. Startup recovery was disabled on the UI wrapper, and the terminal journal made native recovery/synchronization a no-op before this operation.

OLD active generation: **`payload_repair_03a973f7d891b895_b68015aea920`**. Provider watermark: **2026-10-27**. The baseline includes full role/manifest/ownership-artifact hashes, logical WAL-aware queue/approval/source-repair/audit state, journal, scheduler/configuration, relevant code/contracts and market/taxonomy inputs. All role hashes match the completed source-repair journal and active manifest. The exact three selected cases were the only APPROVED ownership cases; six unrelated OPEN reviews and three SUPERSEDED histories remained outside the publication selection.

| OLD binding | SHA-256 |
| --- | --- |
| active manifest | 5797932d9ced7f20c51ecf5d83494646c8270ee0ebd045a03b109946c6966411 |
| analysis | ce5a09a8782660703e5160aa44a798ea2029318732466f0aa90b28c38321e3e8 |
| canonical | 147e6ef965af071062fb89170d62b9bb471267c2cc5ac6cad4278afa2dbba054 |
| provider | 45883cb5083d2847876b29f350387e56d1a0476eb8cfb853fe3e6c5646da123a |
| ownership artifact | 7b7d0cdd9bce7d448b70c7c46af54d3401f4fb0005b4f94f021d29c0e0e460e6 |
| publication journal | 2f22eb0ab73cb0aa75dd509ceca383e6f25f1da77936f8209ffa83549d53def2 |
| scheduler configuration | 3a0b74412a0fb9cf5e7a9b370e97a6d48af031d5094d53b5689669e630c9e894 |

## 2. Exact previously approved inputs

| Ticker | Exact case ID | Candidate fingerprint | Approval fingerprint | Approval timestamp |
| --- | --- | --- | --- | --- |
| GE | 884c628dd47abcff07f81b2c81d0dd48a676c6fd7637e9ace306b7aac5277592 | da2e533a26e5e030604d0eea919f6a190c00035ede18d3b3210680b15c0289c6 | 6752c06ec232aa96efb47583ffc37edfb61286d58f9924f824b62cb018c30496 | 2026-10-28T21:11:06+02:00 |
| RTX | 4e13dd3de19b68f7cede3591268e94cab77f2abb266239a2092b5e2573aabc78 | d5653e48e6a46261e0c37387dbd17cdec622c9aa113a29a37e5488505e0f95fc | 2a8ac68ed045b6826485ebc4a584262cbe825077986c94488cadbe84d2b6c14f | 2026-10-28T21:11:08+02:00 |
| T | 11046955fa9183b592c70add087ee021d1cc627bc12309947c29dd166c9b175b | 87463ed926bfcd1587a7dd1ff04f43bcd64c7d1995daa9231a4d23025c5f8505 | 1bc9a930e30dc1a64dc478d2159093dec50bf205ada38cda7aae65a2f4f9ddff | 2026-10-28T21:11:10+02:00 |

Every selected queue row was APPROVED with result status APPROVED_PENDING_PUBLICATION, publication_required=True and no prior publication metadata. Original operator **Kalle**, note **ok**, exact proposed record, prior review hash/reference, accepted current observation/count/factor/category/security/quarter/equity and approval timestamps all revalidated. `_selected` required the same complete latest canonical basis, unchanged prior history and no conflicting active binding. No new review was approved and no decision text was changed. Publishing operator is Kalle, consistent with the explicitly supplied operator and requested task.

## 3. Source-repair verification

| Ticker | Exact source key | Unchanged repaired observation ID | Unchanged content/full-payload fingerprint |
| --- | --- | --- | --- |
| GE | GE\|ARQ\|2026-10-20\|2026-09-30 | 30891b203267dfa12056544407c8dcdff68edd3001822a4622d975c71d7e2248 | 14eba2facdb54dd1247923e9b684401709621787e8728ee8ab7665551a36e816 |
| RTX | RTX\|ARQ\|2026-10-20\|2026-09-30 | 9dda4193acb8676c52ee8b235e9822b609c4693234323ef25452681d366146f5 | 56b0a3e45b7b69e3308c4e3863aadb44c789746259283cfb0c08fab8361e2e84 |
| T | T\|ARQ\|2026-10-21\|2026-09-30 | 26198cc5927cf7a291d0fcb52eec541a1f16216c31b41670ffb4f9705c8dd2aa | 6f744958e889dc70bbeec7162a795a6cc451e77189fbd34ead8d1a8f07eee577 |

All three payloads still have 112 keys and all approved 83 restored fields, sharefactor=1.0 and finite equity/equityusd, price, marketcap and provider pb. Completeness fingerprints match the source-repair proposal/receipt exactly, native history keys are unique/unambiguous and the latest ARQ report period is still the repaired Q3. Accepted source/provenance equals the approved current quarter, positive ordinary shares, unchanged company/security/category and exact reviewed factor.

Each original source-repair item remains APPROVED/applied with source_repair_only=True, ownership_authorized=False and pb_authorized=False, bound to the completed repair generation. Those are historical source-only decisions, not the authority for this publication. The separate Kalle/ok ownership decisions and this explicit publication task provide the required authority. All source-repair rows remain exactly unchanged after publication. No provider acquisition or source repair ran.

## 4. Original inactive approval candidates

| Ticker | Exact original inactive canonical SHA-256 | Original versioned artifact SHA-256 |
| --- | --- | --- |
| GE | 12a975b9d0e3f6f5a451a323bf89dc735675a87555bd62ccccc1140269d0edc9 | 8f734c87475686ff6fd0098bfb2e08a12668d4ff408058cee7f78360dc35f091 |
| RTX | accf516432f78bcd49bef3448682a37821fba53ec0bfc4bf8d207742f996892c | a458c6c661bbeaa629ff68339a550f3cb8674b1b9ff711d058b6b7aac9040d37 |
| T | d8dfa2258889f42e32625dfa0b771e2f804b1f5859bbed7c90f82a3d1d2e088b | d4e10ce64374063203310dbd8f9d6de7f93567027683687efae2b83878cbdb3c |

All original candidate/export files existed, were not symlinks, matched their frozen approval-result hashes, embedded the exact approved record/artifact pin and passed SQLite quick/FK validation. Their non-ownership financial schema/table content equals the active financial source. Candidate P/B reconstructed under the current market contract. These candidates were verified **as approval evidence only**: their financial copies were not used as publication roles, and no file was silently regenerated under an old approval.

## 5. Fresh candidate generation and scope validation

The unchanged `OwnershipPublicationWorkflow.preview` cloned the current three active roles, froze market data through the existing SQLite backup owner, and merged only the three explicitly selected approved records. All 63 active records remain exactly in their old order; exactly three approved records are appended, giving 66 total. No duplicate/conflicting identity-observation-quarter binding exists. Extra reviews present in cumulative approval artifacts were not implicitly imported.

Preview/generation ID: `pb_ownership_903cf258a97f4873aa0f4797404a61ac`; exact preview hash: `35a111c3fa4dd07fe0cb7a0c642a23aea3ca8ea92da446ccd2b85ed26487b4b4`. The normal deterministic merge yields new artifact SHA **`f8ce2585d4524f397048798f00f822a7274daa0fc706279a5d3554e213a11250`**. Only the two generation-local ownership artifact/configuration tables change. Canonical financial/provenance/publication-authority schema and ordered rows are identical; provider and analysis candidates are byte-identical to OLD. No score/analysis rebuild is required by this ownership-only contract or performed here. All candidate roles passed normal SQLite quick/FK checks.

The six unrelated OPEN reviews were permitted to remain held under the existing selected-case contract. They did not block or join this exact publication set. Fresh readback of their Current P/B business status/value/reason/inputs and provider/history confirms no unrelated release; their queue rows/decisions are identical. AMT/BA/DHR/GM/PNR/PSA and every other pending review were not published.

## 6. Expected and live Current P/B reconstruction

As-of date: **2026-10-28**. All current usable quote dates remain **2026-10-27**; no legitimate price advance changed the prior expected values. Before publication each selected company was held for OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED. After publication all three have **status OK, reason OK** with the exact new-Q approved ownership record. Provider P/B was never substituted for the internal result.

| Ticker | Economic shares, ORDINARY_COMMON | Raw factor | Current usable price | Parent equity USD, Q3 | Live Current P/B |
| --- | --- | --- | --- | --- | --- |
| GE | 1,033,351,921 | 1.0 | 297.6600036621094 | 17,522,000,000 | 17.55436232103115 |
| RTX | 1,349,440,548 | 1.0 | 194.60000610351562 | 69,250,000,000 | 3.7920742076120066 |
| T | 6,736,473,433 | 1.0 | 20.940000534057617 | 106,775,000,000 | 1.3211122199455392 |

Independent Decimal reconstruction at 50-digit precision uses **price × approved economic shares / parent_equity_usd**. Each result matches within 1e-12 relative/absolute tolerance. The exact approved ordinary rule uses new accepted shares directly, without scaling parent equity, reusing prior-quarter shares or inferring a factor from provider pb. The live ownership basis is REVIEWED_SUPPORTED / OPERATOR_CONFIRMED, references the exact Q3 case/observation/hash and accepted share provenance, and retains the existing quarterly-share approximation disclosures.

| Ticker | Shares source date / basis | Approved ownership reference | Independent Decimal P/B |
| --- | --- | --- | --- |
| GE | 2026-10-20 / ACCEPTED_PROVIDER_DATE_QUARTERLY_REVIEW | PB_OWNERSHIP_NEW_QUARTER:884c628dd47abcff07f81b2c81d0dd48a676c6fd7637e9ace306b7aac5277592 | 17.554362321031148464910249971464444698093824905833 |
| RTX | 2026-10-20 / ACCEPTED_PROVIDER_DATE_QUARTERLY_REVIEW | PB_OWNERSHIP_NEW_QUARTER:4e13dd3de19b68f7cede3591268e94cab77f2abb266239a2092b5e2573aabc78 | 3.7920742076120066856225236101083032490974729241877 |
| T | 2026-10-21 / ACCEPTED_PROVIDER_DATE_QUARTERLY_REVIEW | PB_OWNERSHIP_NEW_QUARTER:11046955fa9183b592c70add087ee021d1cc627bc12309947c29dd166c9b175b | 1.3211122199455392049804650995083118707562631702177 |

## 7. Final gates, activation and journal lifecycle

The saved preview and complete logical queue/source baseline were rechecked immediately before calling the normal `publish` with confirmed=True, production_intent=True and operator Kalle. The workflow reacquired its native locks, exact selected approval transaction and source/code/input bindings. It verified original approval artifacts, current financial and ownership merge, all candidate/frozen-market hashes and expected report effects before preparing verified OLD backups.

Before activation it wrote the existing durable GENERATION_POINTER journal, prepared/fsynced the complete NEW generation, then rechecked the OLD active generation/role/manifest/input/code binding, selected approvals and evidence, prepared candidate hashes, frozen market hash and exact journal identity. Atomic pointer activation and normal postflight followed. No active role was manually patched in place.

**NEW active generation: `pb_ownership_903cf258a97f4873aa0f4797404a61ac`.** Outcome COMPLETED; journal operation PUBLISH_PB_OWNERSHIP_REVIEWS; postflight PASSED; rollback/recovery NOT_REQUIRED. Role health/hashes, financial invariance, exact embedded artifact/pin, unchanged market/taxonomy inputs/code/configuration and report effects all passed. The normal completed receipt is archived beside the native preview; no failure, rollback, partial manual repair or queue-only recovery was needed.

| NEW binding | SHA-256 |
| --- | --- |
| active manifest | e1b8075f7c6b3becd5eb2ac439e34b8a102803269ad2b17930de09c84865bd6b |
| analysis | ce5a09a8782660703e5160aa44a798ea2029318732466f0aa90b28c38321e3e8 |
| canonical | b40e552d8a3afd547b08a8c3b66906e5168300c9050180294c45e40c832eb689 |
| provider | 45883cb5083d2847876b29f350387e56d1a0476eb8cfb853fe3e6c5646da123a |
| ownership artifact | f8ce2585d4524f397048798f00f822a7274daa0fc706279a5d3554e213a11250 |

## 8. Published review records and audit

| Audit ID | Ticker | Event | Publication run/generation |
| --- | --- | --- | --- |
| 64 | T | PB_OWNERSHIP_PUBLISHED | pb_ownership_903cf258a97f4873aa0f4797404a61ac |
| 65 | RTX | PB_OWNERSHIP_PUBLISHED | pb_ownership_903cf258a97f4873aa0f4797404a61ac |
| 66 | GE | PB_OWNERSHIP_PUBLISHED | pb_ownership_903cf258a97f4873aa0f4797404a61ac |

Exactly the three selected rows transitioned **APPROVED → PUBLISHED**. Each keeps its original candidate JSON/hash and approval JSON (including operator/note/timestamp) and adds publication binding: generation, artifact SHA, successful-postflight timestamp, candidate/approval fingerprints, publishing operator and run ID. The original preparation result is preserved as historical evidence; the authoritative queue status is now PUBLISHED. Exactly three PUBLISHED events were appended; all prior audit entries remain intact and the normal audit sequence advances by three. No new approval event was added.

All unselected reviews and source-repair decisions remain logically identical. Only selected status/publication-result metadata, three normal audit rows and required sequence metadata changed. Queue validation is row/logical-table based because committed WAL state is part of the queue identity. No main-file-only hash or unsafe main-file queue copy was used.

## 9. Unrelated invariance and watermark semantics

Provider SHA-256 is unchanged, proving no source history, repaired observation, metadata or provider watermark mutation. Analysis SHA-256 is unchanged, preserving all stored scoring/ranking/valuation outputs. Every non-ownership canonical table/schema matches OLD, covering financials, source provenance, identity, publication authority and WFRD reviewed state. All OLD generation files remain byte-identical. Market, scheduler configuration, relevant code/contracts and immutable bundled registries are unchanged. No unrelated ownership publication, publication-authority decision, policy/resolver change or auto-continuation was performed.

The authoritative provider refresh-state row is exactly equal before/after. Published source watermark is **2026-10-27 → 2026-10-27**. The existing ownership publisher passes `old_source_watermark=None` and `new_source_watermark=2026-10-28` (the ownership as-of date) into the generic journal. Those journal field values do not represent a write or advancement of provider refresh state; the provider bytes and actual watermark row are unchanged. No patch was made to force different journal or watermark semantics. Generation publication time is also distinct from provider data freshness.

## 10. Verified retained rollback set

Publication run/generation linkage: **`pb_ownership_903cf258a97f4873aa0f4797404a61ac`**. Retained required rollback role backups: **3**, provider/canonical/analysis; total **2629734400 bytes**.

| Role | Retained backup path | Bytes | Verified OLD SHA-256 |
| --- | --- | --- | --- |
| analysis | /home/kalle/projects/rawcandle/backups/fundamentals_admin_production/pb_ownership_903cf258a97f4873aa0f4797404a61ac/analysis.db | 912031744 | ce5a09a8782660703e5160aa44a798ea2029318732466f0aa90b28c38321e3e8 |
| canonical | /home/kalle/projects/rawcandle/backups/fundamentals_admin_production/pb_ownership_903cf258a97f4873aa0f4797404a61ac/canonical.db | 749371392 | 147e6ef965af071062fb89170d62b9bb471267c2cc5ac6cad4278afa2dbba054 |
| provider | /home/kalle/projects/rawcandle/backups/fundamentals_admin_production/pb_ownership_903cf258a97f4873aa0f4797404a61ac/provider.db | 968331264 | 45883cb5083d2847876b29f350387e56d1a0476eb8cfb853fe3e6c5646da123a |

All three backups independently pass quick/FK verification and match their OLD role hashes. They and the retained OLD generation support the existing full OLD-generation rollback/recovery contract. Backups from earlier source repair also remain retained. No backup cleanup, retention change, restore drill or formal backup acceptance phase was run. Normal native owned preview/candidate/market evidence remains available; no cleanup was added after successful postflight.

## 11. Validation, evidence and Git boundary

Runtime source is unchanged. Repository pytest and full suite: **NOT RUN**, as explicitly requested. Validation used fresh native preflight, exact source/approval/candidate checks, native preview and publication gates, role SQLite checks, independent formula reconstruction, deterministic artifact merge, selected/unrelated report comparisons, exact queue/audit verification and retained OLD backup validation. No source defect appeared; no alternate publisher or manual database fix was introduced.

Native preview/role/frozen-market/completed-journal evidence is under `fundamental_reports/admin_runs/pb_ownership_publications/pb_ownership_903cf258a97f4873aa0f4797404a61ac`. Working before/preview/result evidence is under `/tmp/pb_ownership_publication_ge_rtx_t_20261028/attempt_192143`; log `/tmp/pb_ownership_publication_ge_rtx_t_20261028.log`. Durable independent acceptance/before-state/old-journal/preview/result evidence and checksums are under `backups/fundamentals_admin_production/pb_ownership_903cf258a97f4873aa0f4797404a61ac/publication_evidence`. Only this report is committed; no DB, manifest, journal, queue, backup, runtime artifact/log/cache or unrelated worktree change is included. Push: NO.

## 12. Exactly one recommended next phase

**P/B-OWNERSHIP-ROLLBACK-BACKUP-ACCEPTANCE-1** — formally review/accept the exact retained OLD rollback set and its linkage to this successful publication. Keep all backups; any cleanup requires separate explicit authorization. This task stops after the successful postflight and requested documentation, without starting another operation.
