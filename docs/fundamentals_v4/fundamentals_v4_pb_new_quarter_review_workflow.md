# P/B.12 — Operational new-quarter ownership review

Implementation and inactive-copy validation only, 2026-10-08. No Production publication, active-generation change, live registry repin, scheduler change or push. Baseline: `27a53c70162da923f2149cc70409771147f3f1e6`; active generation remains `pb_quarterly_ownership_v2_20261008T080025Z`.

## Trigger and scope

Normal `phase12d.reconcile_canonical` detects when the latest accepted quarter's observation/hash/quarter differs from a previously supported V2 observation. Both Admin refresh copy paths pass the existing operational queue path. Direct reconciliation returns structured candidates when no queue is supplied. Detection runs after financial acceptance; queue failures become explicit result diagnostics and do not undo financial acceptance. No independent scheduler is added.

Only previously `REVIEWED_SUPPORTED` scopes qualify: the existing 16 ordinary, six ADR-factor and nine identity overrides. The 378 ownership holds and all other unreviewed companies remain excluded. V1 configuration and reporting before the V2 effective date produce no candidates. New accepted parent equity, provider reference and four-quarter history update normally while Current P/B alone requires observation-bound review. No previous-quarter share fallback exists.

## Candidate schema and classification

The structured candidate contains `company_id`, company key, ticker and security ID; complete previous reviewed identity, security form, ownership interpretation, review reference/hash, official evidence URLs and exact rational factor; previous/new fiscal year, quarter, report period, observation ID/content hash, provider/availability dates, raw shares/factor/category and parent equity; accepted share provenance; active securities and validity dates. Deltas include absolute/percentage shares, factor, category, identity, quarter, parent equity and provenance. New economic units under the prior exact factor are explicitly hypothetical.

The case key hashes company ID plus the new observation/hash/quarter/report period. A separate candidate hash covers the full candidate, including prior review and registry SHA. Volatile processing timestamps and filesystem paths do not enter that hash. Updates to the same observation's relevant binding regenerate its candidate hash; a distinct observation/revision creates a new case.

Classification is conservative:

| Classification | Condition |
|---|---|
| `CONTINUATION_CANDIDATE` | Same issuer/security, one active class, valid accepted positive finite shares, matching share provenance, compatible category and unchanged raw factor |
| `REVIEW_REQUIRED_IDENTITY_CHANGE` | Issuer/security/ticker or security validity differs |
| `REVIEW_REQUIRED_FACTOR_CHANGE` | Raw provider factor differs |
| `REVIEW_REQUIRED_CLASS_OR_PERIMETER_CHANGE` | Multiple active securities or incompatible category/security form |
| `REVIEW_REQUIRED_INVALID_SHARE_BASIS` | Invalid shares, accepted-count mismatch, missing observation/hash or inconsistent provenance |
| `REVIEW_REQUIRED_OTHER` | Missing dates or an existing explicit share-change restriction |

A changed share count, including a large percentage change, is allowed as a candidate and never auto-approved. Known identity overrides may retain their false-positive provider category or move to a compatible common category. ADR factors reuse the prior official exact numerator/denominator only after explicit confirmation. Rounded provider factors must remain exactly unchanged for this bounded continuation path. Raw zero is preserved without ticker branches or inferring a ratio from marketcap/P/B. No external corporate-action completeness feed is required. Conflicts need separate evidence resolution and cannot use the continuation action.

## Queue and Admin workflow

The existing queue's generic table has ticker as its primary key. Reusing it would overwrite provider/publication reviews and earlier-quarter history. A bounded `pb_ownership_review` child table in the **same queue database**, using the same existing audit table and Admin Review Queue panel, therefore stores these cases. This is not a second generic review system. Publication-authority semantics remain unchanged.

1. Run the normal Fundamentals refresh. Financial acceptance creates `PB_OWNERSHIP_NEW_QUARTER` cases automatically.
2. Open the existing Admin Review Queue and refresh its list. The ownership section shows old → new quarter, ownership type, shares/percentage delta, raw and exact factors, categories, classification, lifecycle status and Current P/B impact. Include resolved cases to inspect history.
3. Choose **Approve quarterly ownership continuation** for one open continuation candidate. The dialog first performs a fresh read-only preview, showing exact observation/hash, prior reviewed Current P/B reference with its reference date, new-Q held status, hypothetical P/B, new shares, current price and new parent equity.
4. Enter an operator name and review note, then explicitly select confirmation of the displayed quarterly basis. The button stays disabled until all three are supplied. The backend independently requires literal `True`, nonempty operator/note, the exact case ID/hash and a still-current candidate. There is no approve-all action.
5. Alternatively choose **Keep on hold** and enter a note. This records the decision and leaves the case/history visible. Held cases are not silently reopened by unchanged refresh retries; changed evidence regenerates the candidate.
6. Approval returns the inactive canonical candidate path and leaves the case `APPROVED`, pending separately authorized controlled publication. It does not activate any generation.

Before approval, recompute the full candidate from the canonical read transaction and require the same hash. This verifies observation/hash, quarter, count, factor/category, security, prior review and artifact version. Changed, superseded or resolved candidates fail closed. Duplicate approval is safely rejected as not open. Admin uses its existing operation lock, Production lock and publication-recovery guard around preparation; no direct live financial write is introduced.

## Append-only evidence and candidate preparation

The bundled `ownership_reviews_v2.json` stays byte-identical and remains readable by old generations. New artifacts use `ownership_reviews_v2.<sha256>.json` in an exclusive case/hash output directory. JSON serialization sorts keys, uses stable existing-record order and appends new records; old records are retained exactly. Duplicate observation bindings and additions outside prior supported identity scopes are rejected. Previously approved operational records are included when preparing subsequent candidates, so approvals for different companies can coexist.

The canonical candidate embeds the complete versioned artifact in additive `v4_pb_ownership_artifact`; its existing generation-local reporting configuration pins the exact payload SHA. A generation lacking embedded evidence continues using the immutable bundled registry. A mismatching pin/payload fails closed. Legacy bundled-registry repinning is refused for embedded artifacts to prevent dropping history.

Every appended review binds exact new identity, observation/hash, fiscal quarter/report period, sharesbas, raw factor, category and provider/availability dates. It records operator, timestamp, note, `OPERATOR_CONFIRMED`, prior evidence reference/hash and retained official URLs. Exact official ADR ratios are retained without estimation. V1 is never edited.

Approval backs up the source canonical into an inactive output lane, embeds the artifact and repins **that candidate only**. Rehearsal checks its Current P/B against the preview and checks Provider P/B/history equality. Failures remove the candidate lane and roll back queue approval. Approval returns the source canonical SHA as a later publication gate. No global registry cache mutation or live DB mutation is used.

Current P/B remains reporting-only, with the unchanged calculation:

`current price × approved new-quarter economic units / new accepted parent_equity_usd`

Ordinary economic units equal new accepted sharesbas. ADR units equal new accepted sharesbas times the approved exact rational factor. Existing equity/price freshness, parent-equity and corroboration gates still apply. Review approval alone does not guarantee availability when another gate fails. The quarterly-share approximation disclosure remains unchanged.

## Publication and remaining operator steps

This phase deliberately does not publish. An ordinary Refresh Production run does not automatically import pending approval artifacts. Keep the returned canonical candidate and versioned artifact for a separately authorized controlled immutable-generation publication using the established P/B.11 process:

1. Reacquire normal Production/scheduler and taxonomy locks and recovery guards. Verify the active manifest, provider/analysis inputs and returned `source_canonical_sha256` still match the reviewed source. If financial source state changed, regenerate/revalidate against the new accepted observations; never publish a stale backup.
2. Pair the reviewed canonical candidate with the matching provider and analysis candidates. Verify embedded artifact/pin, full candidate hashes, unchanged non-P/B outputs, and affected P/B results with frozen market inputs. No manual DB-row inspection or JSON editing is needed to create the reviews.
3. Use existing verified backups, candidate manifest, publication journal, `prepare_generation_from_candidates`, final source/hash gates and atomic prepared-generation activation. Run normal postflight and journal completion. Publication remains a separate human-authorized operation; this review action provides no publish shortcut.
4. Synchronize the ownership queue against the now-active canonical (`RefreshReviewQueue.sync_ownership`). Successful normal Production refresh also performs this bookkeeping after journal completion. Only an artifact containing the exact approved record **and** the authoritative active canonical path can mark the case `PUBLISHED`. Synchronizing an inactive candidate cannot consume approval.

Retries create one logical case per accepted observation. Unchanged retries create no duplicate audit entries. Later observations preserve old decisions as superseded history. Approved records/history remain auditable; pending approval persists until controlled publication. No daily review or share scheduler is needed for an unchanged accepted quarter.

## Validation

Four synthetic next-Q rehearsals use the real provider ingestion fixture and normal `reconcile_canonical`, on isolated SQLite databases, with Q2 shares 100/equity 1,000 and Q3 shares 120/equity 2,000. Current price is 20. Each detects a held new Q, previews, explicitly approves, embeds/repins the candidate, verifies the exact appended record, repeats reconciliation and verifies next-day price behavior. Source files remain unchanged by approval; candidate non-ownership tables remain identical. Tests do not publish; an injected active-path predicate exercises consumption semantics without changing the real active manifest. Pytest removes synthetic temporary databases.

| Case | Raw factor | Exact factor | Before Q3 acceptance | Held Q3 | Approved Q3 | Next day, price 30 |
|---|---:|---:|---:|---|---:|---:|
| Ordinary | 1 | 1 | 2 | Review required | 1.2 | 1.8 |
| Identity override | 1 | 1 | 2 | Review required | 1.2 | 1.8 |
| ADR | 0.333 | 1/3 | 2/3 | Review required | 0.4 | 0.6 |
| Zero provider factor | 0 | 1/40,000 | 0.00005 | Review required | 0.00003 | 0.000045 |

Focused tests cover the 30 requested behaviors, stale observation/hash/identity/count/registry cases, explicit holds, queue failures, later revision history, generation payload tampering, immutable files, isolated score/provider storage and Admin dialog confirmation. The existing reporting, ownership V1/V2, review queue and operational rebuild modules are focused checks; the **one additional regression group is `tests/test_fundamentals_admin_ui.py`**. Full suite not run.

Read-only comparison with baseline HEAD verified exact equality of all 2,542 active-security P/B reports at 2026-10-08, including providers/history/reasons/metadata. This is an all-active-security invariance check, **not** the P/B.11 2,468-member coverage denominator. No new live candidates were detected. Whole-file SHA checks verified the three live roles, active manifest, V1/V2 bundled registries and operational queue remained unchanged; the analysis role includes stored valuation/fundamental scoring state. The compact CSV records evidence and final test results. Initial fixture setup/digest errors were corrected before the final passing runs.

Final verification: **379 distinct targeted cases passed**: 36 new workflow cases (35 in the complete workflow run, plus the final multi-class guard case separately), 194 existing focused reporting/ownership/queue/reconciliation cases, 90 normal Admin copy/Production refresh cases and 59 Admin UI regression cases. Commands:

```sh
pytest -q tests/test_fundamentals_pb_new_quarter_review.py
pytest -q tests/test_fundamentals_pb_new_quarter_review.py -k new_active_class
pytest -q tests/test_fundamentals_pb_reporting.py tests/test_fundamentals_pb_ownership.py tests/test_fundamentals_pb_quarterly_ownership.py tests/test_fundamentals_admin_refresh_review_queue.py tests/test_phase12d_operational_rebuild.py tests/test_fundamentals_admin_ui.py
pytest -q tests/test_fundamentals_admin_refresh_production.py tests/test_fundamentals_admin_refresh_copy_test.py
```

No full suite, Production rollout, active-generation activation or push was performed.
