# P/B ownership provider-factor null audit

2026-10-28. Audit/root cause only. No ownership approvals, source edits, runtime writes, network acquisition, Refresh Preview/Test/Production or push.

**GE, RTX and T reproduce the exact 1.0 → None ownership-review pattern. The common primary root cause is INGESTION_FACTOR_LOSS, not proven benign provider-null identity semantics.** The current stored provider JSON is a 29-field financial projection; it omits sharefactor entirely. It also omits equity/equityusd, price, marketcap and pb. For eight prior quarters per company, a retained generation contains the complete 112-field original payload with factor '1.0'; all 24 matching current payloads exactly equal normalization of those originals. Their normalized hashes also match the current stored content hashes. Valid factor evidence was lost with the other unprojected fields.

The current Q3 HTTP response bytes were not retained in the evidence inspected. Its true upstream factor cannot be recovered from the projected payload, so this audit does **not** claim the provider returned null, omitted an identity default or definitely supplied 1.0 for Q3. The proven historical loss, common projection/run and absent P/B fields identify the lossy ingestion route; they do not authorize inventing the missing Q3 values.

**Keep strict fail-closed review. Do not equate None with 1.0.** All three currently lack accepted equity and native price/cap corroboration, not only factor. They are **NOT_SAFE_TO_APPROVE** through continuation on the available evidence; the UI also correctly disables that action. Raw source completeness must be repaired before any later ownership decision. No review was approved, held, reopened or synchronized in this audit.

## Governing contracts and frozen scope

The [quarterly ownership V2 contract](fundamentals_v4_pb_quarterly_ownership_durability_v2.md), [operator continuation workflow](fundamentals_v4_pb_new_quarter_review_workflow.md), [ownership-factor contract](fundamentals_v4_pb_ownership_contract_v1.md) and [P/B reporting contract](fundamentals_v4_pb_reporting_v1.md) govern. P/B remains reporting-only, outside Valuation Score, using current usable price × accepted quarterly validated economic units / accepted quarterly parent_equity_usd. Provider P/B remains separate. The [economic-units audit](pb_review_economic_units_audit_2026-10-28.md) established that the earlier apparent 10× mismatch was a screenshot-transcription discrepancy; no factor-ten correction is relevant here.

Only the ownership cases, their provider/canonical/market provenance, eight previous quarters plus current Q3, the exact originating refresh batch, relevant internal actions and directly governing source were inspected. No all-ticker history or web search was performed. The complete ownership queue contains nine OPEN rows, all frozen read-only. Existing pure detector and ownership review preview were used; no Refresh Fundamentals workflow was run. No writer, schema initializer, candidate creation, artifact export or approval function was called.

Starting HEAD: `18af44ea097c0ad479db594eb78d239ee1a5a013`. Baseline captured `2026-10-28T13:24:08.784424+00:00`; final invariance verification `2026-10-28T13:31:44.613674+00:00`. Active generation: `refresh_20261028T054130Z_refresh_fundamentals_f0854217d4df_production_14d59fd7`. Provider watermark: **2026-10-27**, successful run `20261028T054130Z_refresh_fundamentals_f0854217d4df_production_14d59fd7`, completed `2026-10-28T05:44:22Z`; unchanged. Ownership artifact pin: `7b7d0cdd9bce7d448b70c7c46af54d3401f4fb0005b4f94f021d29c0e0e460e6`.

## 1. Exact GE / RTX / T review cases

All three are OPEN, FY2026 Q2 → FY2026 Q3, classification REVIEW_REQUIRED_FACTOR_CHANGE. Prior/new category is exactly Domestic Common Stock Primary Class; prior factor 1.0, current normalized factor None. Each has one active canonical security, a valid accepted positive share count and the same identity binding. The classification reason is the exact `new.sharefactor != previous.provider_declared_factor` comparison.

| Case | Company / security / company key | Previous → current shares | Exact shares change % | Prior → current provider date | Prior → current report period | First / last seen UTC |
| --- | --- | --- | --- | --- | --- | --- |
| GE | 931 / 934 / SEC_CIK:0000040545 | 1037562513.0 → 1033351921.0 | -0.4058157409547847 | 2026-07-16 → 2026-10-20 | 2026-06-30 → 2026-09-30 | 2026-10-22T04:28:24Z / 2026-10-22T04:28:24Z |
| RTX | 1928 / 1938 / SEC_CIK:0000101829 | 1347758144.0 → 1349440548.0 | 0.12482981516304115 | 2026-07-23 → 2026-10-20 | 2026-06-30 → 2026-09-30 | 2026-10-22T04:28:24Z / 2026-10-22T04:28:24Z |
| T | 2123 / 2133 / SEC_CIK:0000732717 | 6852385650.0 → 6736473433.0 | -1.6915600335483116 | 2026-07-22 → 2026-10-21 | 2026-06-30 → 2026-09-30 | 2026-10-22T04:28:24Z / 2026-10-22T04:28:24Z |

T's exact counts are **6,852,385,650 → 6,736,473,433**, rather than the approximate 685m → 674m transcription in the request. The percentage change is the same; the exact system values take precedence. No case drift was observed relative to the existing economic-units audit: case IDs/hashes and all nine queue rows remain identical to the new audit baseline.

**GE:** case `1e66dce85311e9134d6d0b0a40e10f7f12837005437289b71da3c29ffbba1d39`; candidate fingerprint `9351832d83e7a3d544477289ae8806f8fdfebe09e2316fc6065b81b8c2cd85a6`. New observation `5806bfc4a10a7d809ef83498c8360b26660ce28502d81408e7b189426a2cab24`, content hash `d47fcb1f67a85963201f7d0c0745672e6ba99bb75c9c7ad50f8581cfdcb86375`. Prior reviewed observation `d0b7209468d4adc6f60556c8ddca96b8119f1c8298ef7744222d4d08a24db2cb`, content hash `2411ac47fbe639e29219814fe86af6027f75e0e7423f82642ae471b24380af0d`. Accepted quarter_id `33069`; shares provenance `392421`, SHARADAR / sharesbas → shares_outstanding / DIRECT / `SHARADAR_ARQ_PRIMARY_V1`. New observation/hash matches accepted parent-equity source and share provenance exactly.

**RTX:** case `5b70038a5aa7d5c2b280fefa65fb2dadb44028455a9763f21d23f7b5eaa69f91`; candidate fingerprint `cdcd4ee6d28cd294544cbf6a69dfa9ff13e9d7d61bcaf1fe9ededf9fe38be35c`. New observation `bfd42bf2f633cfb8e511931673bc6769ea1bad22859c227d602d7328d42ea4f1`, content hash `50238350ed044491f6198bbb922dc0a562f2badfc46bde9ad266a8ed6d6462ec`. Prior reviewed observation `8cb149dd4dd406c639eccf945b6b389bfe4dd6878c300003ed9d89734b01e59b`, content hash `c92f7798069e87efb5b78694e9e6798e27ef9a7e21d3e99471c4c74aa49620e6`. Accepted quarter_id `68896`; shares provenance `818019`, SHARADAR / sharesbas → shares_outstanding / DIRECT / `SHARADAR_ARQ_PRIMARY_V1`. New observation/hash matches accepted parent-equity source and share provenance exactly.

**T:** case `3b6e2b53618aec3a7bff5819d79356d1f6c451f0ca1159cf4b46920e75a37acd`; candidate fingerprint `1384781f425609bcfd089ff506d47255df5a41ab933770e3ed6316a5254e5121`. New observation `a04ecf0968eaee10a2018c39e9d80057e59520770412d784f518bdd0c3ad6e1c`, content hash `0fbe9ab6418a1f910f4bb40dc6231889a9c91e423354b94d43075c173e500be0`. Prior reviewed observation `2a41943563bbc73ad719b6577bc462e9b9c1025f543851af0957a307ca319e75`, content hash `f65beea98b6ecf772cb5b3884119c81779e4fbc9f55a09a42c916ce4a6e141df`. Accepted quarter_id `75635`; shares provenance `897907`, SHARADAR / sharesbas → shares_outstanding / DIRECT / `SHARADAR_ARQ_PRIMARY_V1`. New observation/hash matches accepted parent-equity source and share provenance exactly.

The queue's current_pb_status is OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED. The fresh report instead returns **NOT_AVAILABLE / MISSING_EQUITY**, because the equity gate runs before ownership validation. These describe different layers and are not contradictory. No hypothetical P/B is computed by the normal review preview for a factor-change classification. All approval_json/result_json fields remain NULL.

## 2. Provider factor definition and representation

The upstream field is Sharadar fundamentals/SF1 **sharefactor**. Its contract meaning is a dimensionless ownership/security-economic-unit ratio used with source-price shares to corroborate capitalization, including ADR/ADS and class economics. It is not a decimal scaling flag for equity or a generic price split-correction instruction. The [earlier provider source audit](fundamentals_v4_pb_current_marketcap_source_audit.md) and [book-equity investigation](fundamentals_v4_pb_book_value_investigation.md) retain the source-definition evidence; no external refetch was necessary or authorized.

The displayed “Provider factor” is `case.previous.provider_declared_factor → case.new.sharefactor`. The latter originates at `provider_observation.payload_json.sharefactor`, becomes `finite(raw.get('sharefactor'))` in [parent_equity acceptance](../../rawcandle/fundamentals/schema/parent_equity.py#L20), and is stored as REAL in v4_parent_equity_source.sharefactor. [latest_basis](../../rawcandle/fundamentals/admin/pb_ownership_review.py#L43) selects it into the case and the queue persists that case JSON. The provider native typed financial table does not contain a sharefactor column; the retained raw JSON is essential.

A present numeric '1.0'/'1'/1 becomes float 1.0 and denotes identity in these ordinary cases. The finite helper maps missing keys, JSON null, blank/non-numeric and nonfinite inputs to None. That representation alone cannot distinguish the reasons. Here the key is **absent**, not a present JSON null and not a numeric parse failure. Absence in a lossy stored projection is not an upstream contractual declaration of “not applicable” or “identity.”

In reviewed ordinary ownership, the economic multiplier is explicitly 1.0 because of the approved ORDINARY_COMMON interpretation. In ADS ownership, it is the independently reviewed exact positive numerator/denominator, not the rounded provider factor. The raw provider factor is still required to match the bound review as evidence. No provider factor multiplies parent equity. Raw None has no generic identity/default fallback in classification or the unreviewed common gate.

## 3. Raw prior/current evidence and the first loss point

Current accepted observations are stored under provider SHARADAR, native_table fundamentals, dimensions ARQ/MRQ; the three current ARQ rows were inserted by `REFRESH_COPY_4d40fa311c02d4162e9c` at **2026-10-22T04:34:40Z**. That run covered 15 tickers and was published by existing Production run `20261022T043408Z_refresh_fundamentals_bb23ca223d59_production_eb6f648d`. These are historical read-only evidence, not workflows run for this audit.

| Case | Prior raw sharesbas / raw sharefactor | Current stored raw sharesbas / factor | Current key count | Current source date / lastupdated | Provider record key |
| --- | --- | --- | --- | --- | --- |
| GE | '1037562513' / '1.0' | 1033351921 (int) / key absent | 29 | 2026-10-20 / 2026-10-21 | GE\|ARQ\|2026-10-20\|2026-09-30 |
| RTX | '1347758144' / '1.0' | 1349440548 (int) / key absent | 29 | 2026-10-20 / 2026-10-21 | RTX\|ARQ\|2026-10-20\|2026-09-30 |
| T | '6852385650' / '1.0' | 6736473433 (int) / key absent | 29 | 2026-10-21 / 2026-10-21 | T\|ARQ\|2026-10-21\|2026-09-30 |

The exact prior reviewed observation IDs no longer exist in the active provider DB because complete-history replacement removed/reinserted them. They were recovered by **exact observation ID and content hash** from retained generation `pb_quarterly_ownership_v2_20261008T080025Z`, provider DB SHA-256 `2b3a57add8b51413d98f220d4cdd313994d1a4079f987a94796bf6a2b6db5fbb`. That retained DB remained byte-identical throughout. No older observation was substituted into a current P/B calculation.

The first loss point is the old refresh projection. Before commit `f23af13e7086296b1c917dcc5d2c25ca7accb3f6` (2026-10-26), validate_complete_history kept only `normalize_source_row(row)`, and replace_provider_histories persisted `payload = dict(item)`. That normalizer deliberately selects source/fiscal keys plus the financial-field tuple: exactly 29 fields here. sharefactor, equity/equityusd, price, marketcap, pb and other provider extras do not belong to that tuple. Their absence was therefore introduced before the JSON labelled provider payload was persisted.

Proof is stronger than a missing-key inference: **24 same-source-key historical pairs** (eight per issuer) reproduce the current payload exactly by applying that normalizer to the retained full 112-field payload. Their normalized _raw_row fingerprints equal the current content hashes. All 24 old factors are present '1.0'; all 24 current factor keys are absent. No financial revision is needed to explain the difference. The code path can therefore erase a valid factor. The current stored Q3 payload has exactly the same 29-key projection shape and common refresh origin.

Origin classification for all three: **NORMALIZATION_REMOVED_VALUE within lossy ingestion**, corresponding to primary root cause **INGESTION_FACTOR_LOSS**. It must not be labelled RAW_PROVIDER_NULL. The precise Q3 wire value is unavailable; the recovered older data proves the loss mechanism and historical valid-factor removal, not a new Q3 identity factor. Current provider_status SUCCESS and a valid semantic content hash do not prove retention of all originally acquired fields.

## 4. Bounded historical sequence: current Q3 plus eight prior quarters

The eight prior source keys in each retained generation have full payloads and factor '1.0'. The active generation contains matching financial projections with no factor key for all of them. The current Q3 source key has no corresponding October 8 observation. Historical category is not embedded in these financial payloads: the prior reviewed Q2 category and the unchanged archived/current SF1 metadata establish category continuity, not a fabricated per-quarter category history.

| Case | Fiscal quarter / report period | Shares in current source | Factor in retained full source | Factor in current stored projection | Current observation ID | Same-key normalized payload/hash match |
| --- | --- | --- | --- | --- | --- | --- |
| GE | 2026-Q3 / 2026-09-30 | 1033351921 | Q3 source not in Oct 8 archive | absent → None | 5806bfc4a10a7d809ef83498c8360b26660ce28502d81408e7b189426a2cab24 | not available |
| GE | 2026-Q2 / 2026-06-30 | 1037562513 | 1.0 | absent → None | b7819f1a82ec004b3a4520311180fb750f3e695a590c7ecdd1c434f6b6e7d806 | YES / YES |
| GE | 2026-Q1 / 2026-03-31 | 1043337235 | 1.0 | absent → None | c60b055082e2111fc7c0b056f454fff362d3bc5ce71649ac577a8ff01eb2fec4 | YES / YES |
| GE | 2025-Q4 / 2025-12-31 | 1048813612 | 1.0 | absent → None | affd3095265bc4def27f249a6cd203a3f9ade3ded1883601f28f6477f390b122 | YES / YES |
| GE | 2025-Q3 / 2025-09-30 | 1054813911 | 1.0 | absent → None | 0d7ba3fdd3734fd5622e9224421dad936e6f183c9962adc110297ea94dc618b2 | YES / YES |
| GE | 2025-Q2 / 2025-06-30 | 1060439387 | 1.0 | absent → None | 3d46f00192dbb3c85ea68ad52f539da03e84759ecf2df4030d9bdb76736db518 | YES / YES |
| GE | 2025-Q1 / 2025-03-31 | 1066386643 | 1.0 | absent → None | 75e372ce89a4092b5d90d730f2e21b2b3bb5e5a7740c251f03e74ba0f8938878 | YES / YES |
| GE | 2024-Q4 / 2024-12-31 | 1073290505 | 1.0 | absent → None | 05ff382c12de466833f9e3c7eb2b912d450ab471921e222695aee0700efb2a99 | YES / YES |
| GE | 2024-Q3 / 2024-09-30 | 1082294004 | 1.0 | absent → None | d7658efad66e6edcac4e45b51177e6fc09f6093b45a44bf426e638a00b0876c1 | YES / YES |
| RTX | 2026-Q3 / 2026-09-30 | 1349440548 | Q3 source not in Oct 8 archive | absent → None | bfd42bf2f633cfb8e511931673bc6769ea1bad22859c227d602d7328d42ea4f1 | not available |
| RTX | 2026-Q2 / 2026-06-30 | 1347758144 | 1.0 | absent → None | edfb7ebc36139fb82776f467896b196f2fcfc4ad304c7b89962b3ba40e47e957 | YES / YES |
| RTX | 2026-Q1 / 2026-03-31 | 1346683428 | 1.0 | absent → None | 25a6feed6cf3abed6b5038b64d39ac5fe61ddcfc472623676ee652686e962b24 | YES / YES |
| RTX | 2025-Q4 / 2025-12-31 | 1342287676 | 1.0 | absent → None | abdc200173afb0d60f8666707bdab2ef74bd05dd4f9ce07e25b502cd48099369 | YES / YES |
| RTX | 2025-Q3 / 2025-09-30 | 1340771942 | 1.0 | absent → None | 3e17e17b9ec82fd2e0f942bd6691d4583ba775c381d895d87e5909e8af176558 | YES / YES |
| RTX | 2025-Q2 / 2025-06-30 | 1338541827 | 1.0 | absent → None | 35abcf3afe84335ad65e58a20c9ef13a98d5530718eb22be0dad7c0945bedfee | YES / YES |
| RTX | 2025-Q1 / 2025-03-31 | 1335953770 | 1.0 | absent → None | d4851874a414e26a4188d329bd6a87e8e28a8d3def2dacb1a7779d512c3c1d5a | YES / YES |
| RTX | 2024-Q4 / 2024-12-31 | 1332122758 | 1.0 | absent → None | 9578d76a0f398481dd35268f0be2f3cfdd1826a2abb763972fb8b6e899e28e63 | YES / YES |
| RTX | 2024-Q3 / 2024-09-30 | 1331016397 | 1.0 | absent → None | fba0ce948453d4b2aa4d0b39fcaa3255820112cdee7603acce717c77d9580c6f | YES / YES |
| T | 2026-Q3 / 2026-09-30 | 6736473433 | Q3 source not in Oct 8 archive | absent → None | a04ecf0968eaee10a2018c39e9d80057e59520770412d784f518bdd0c3ad6e1c | not available |
| T | 2026-Q2 / 2026-06-30 | 6852385650 | 1.0 | absent → None | b0e6c320b41e1136b35fae88cbf90c7c7b36a1ce73771aca9c80d98c278b0d42 | YES / YES |
| T | 2026-Q1 / 2026-03-31 | 6948338835 | 1.0 | absent → None | b0100a0ae7332fd31704c205001580ca32f8f41625c283ba58da34bb6c16a965 | YES / YES |
| T | 2025-Q4 / 2025-12-31 | 7000577201 | 1.0 | absent → None | d5a14d93003f48961aa4a563d25592bf24279eb9b2d34826476155ad5d91acba | YES / YES |
| T | 2025-Q3 / 2025-09-30 | 7089449495 | 1.0 | absent → None | f6bbbfcb35c3c6b44320d64164cc6427ef33632c7ed08b0113cf7e38b9735256 | YES / YES |
| T | 2025-Q2 / 2025-06-30 | 7150385480 | 1.0 | absent → None | a5f978b478c11019ca9adfebe3c4acf10ea257e0c897fc7ffd2a20fcda92c747 | YES / YES |
| T | 2025-Q1 / 2025-03-31 | 7195602178 | 1.0 | absent → None | 51e37c5ed6306813d60ef32b715f09c3c637275ad89db3166df13fdebeaf40a5 | YES / YES |
| T | 2024-Q4 / 2024-12-31 | 7178183000 | 1.0 | absent → None | 71d96723a608792299cc4c5c13bf3a4e4f3447692be753a34518b90231f0118d | YES / YES |
| T | 2024-Q3 / 2024-09-30 | 7175289157 | 1.0 | absent → None | d7a59905037648939e986e3f58e4c177fcc7536148203e5c34751b768b7f0c93 | YES / YES |

The archived sequence shows identity factor through the eight available prior quarters. The active stored sequence shows uniform omission after replacement, not intermittent provider-reported nulls. No observed factor flip is tied to a category change, verified split or class conversion. Shares remain the accepted filing-based share counts; the normalizer does not apply a split multiplier or change a positive integer sharesbas value. Counts differ by quarter as reported. These sequences cannot establish Q3 factor semantics from old-quarter carry-forward.

## 5. Whole P/B path and economic effect

| Stage | Observed behavior |
| --- | --- |
| 1. Raw provider shares | Current stored GE 1,033,351,921; RTX 1,349,440,548; T 6,736,473,433; positive integers. |
| 2. Raw provider factor | Current stored payload omits key; original Q3 wire value unavailable. Prior exact/full source has string 1.0. |
| 3. Canonical normalized factor | finite(raw.get(sharefactor)) → None; projection correctly retains that missing state. |
| 4. Economic-share suggestion | detect uses prior reviewed ORDINARY_COMMON rule → raw new shares × 1. This field is explicitly hypothetical, not accepted ownership. |
| 5. Ownership comparison | Same identity, one active class, valid shares/provenance; None != previous 1.0. |
| 6. Review classification | REVIEW_REQUIRED_FACTOR_CHANGE, OPEN; no default replacement by one. |
| 7. Hypothetical continuation | Normal preview returns hypothetical_current=None for this classification; no candidate prepared. |
| 8. Actual P/B eligibility | Current report stops at MISSING_EQUITY; the unchanged ownership artifact also has no exact new-Q review. No current numeric P/B. |
| 9. Approval/publication eligibility | List action disabled; backend independently requires OPEN plus CONTINUATION_CANDIDATE and explicit confirmation. No approved record exists to publish. |

Three isolated in-memory counterfactuals per case identify the distinction between raw factor evidence and economic multiplier. They use real new-quarter rows/quotes and existing pure helpers only. Hypothetical records are supplied as local Python values; nothing is written, approved or installed.

| Case | Actual factor / actual P/B | P/B with only factor set to 1.0 | Classification if only factor set to 1.0 | Units with an in-memory exactly matched None review | Units with an in-memory exactly matched 1.0 review | Price × ordinary units USD |
| --- | --- | --- | --- | --- | --- | --- |
| GE | None / NULL (MISSING_EQUITY) | NULL (MISSING_EQUITY) | CONTINUATION_CANDIDATE | 1033351921.0 | 1033351921.0 | 307587536589.1078 |
| RTX | None / NULL (MISSING_EQUITY) | NULL (MISSING_EQUITY) | CONTINUATION_CANDIDATE | 1349440548.0 | 1349440548.0 | 262601138877.13147 |
| T | None / NULL (MISSING_EQUITY) | NULL (MISSING_EQUITY) | CONTINUATION_CANDIDATE | 6736473433.0 | 6736473433.0 | 141061757284.68494 |

Existing exact ordinary reviews could in principle explicitly bind raw None: the evaluator compares raw evidence exactly and then uses the independently reviewed ordinary interpretation to multiply shares by 1. It does **not** infer that None equals 1.0. The counterfactual None row against a 1.0-bound record returns OWNERSHIP_REVIEW_UNVERIFIED, whereas matched None and matched one records produce the same ordinary economic units. No such new-Q None review is authorized or present here.

In all three cases both counterfactual current_pb calls still return MISSING_EQUITY and NULL value. Accepted current equity/equityusd, native price, marketcap and Provider P/B are also missing from this source projection. A meaningful numerical P/B with factor one cannot be computed without inventing additional inputs. The table's hypothetical capitalization is arithmetic only; it is not a validated market-cap result or a candidate P/B. Old Q2 equity is deliberately not substituted.

Thus raw provider factor affects **review classification, exact review binding, generic ordinary eligibility and approval eligibility**. It is not a direct multiplier of these three reviewed ordinary share counts or P/B denominator. In ADS paths a separately reviewed unit ratio does affect economic shares and P/B numerically; dropping raw-factor binding because ordinary multiplication uses one would weaken provenance across supported security types.

## 6. Ordinary continuation comparison

All nine current cases were freshly detected and compared by full candidate fingerprint; raw accepted source factor and shares provenance were checked. Five requested normal controls plus PSA provide six 1.0 → 1.0 continuations.

| Case | Shares old → new | Change % | Factor old → new | Category unchanged | Accepted shares provenance | Classification | Fresh hypothetical P/B |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AMT | 465960048.0 → 463763555.0 | -0.47139084336260684 | 1.0 → 1.0 | True | same new observation / DIRECT | CONTINUATION_CANDIDATE | 24.243205131327542 |
| BA | 790370020.0 → 792449940.0 | 0.26315775489560433 | 1.0 → 1.0 | True | same new observation / DIRECT | CONTINUATION_CANDIDATE | 20.35653354286288 |
| DHR | 702986054.0 → 703530815.0 | 0.07749243344163936 | 1.0 → 1.0 | True | same new observation / DIRECT | CONTINUATION_CANDIDATE | 3.0439407896160087 |
| GE | 1037562513.0 → 1033351921.0 | -0.4058157409547847 | 1.0 → NULL | True | same new observation / DIRECT | REVIEW_REQUIRED_FACTOR_CHANGE | NULL |
| GM | 877451541.0 → 843549423.0 | -3.8637025996174024 | 1.0 → 1.0 | True | same new observation / DIRECT | CONTINUATION_CANDIDATE | 1.0817353644669707 |
| PNR | 159637950.0 → 159654682.0 | 0.010481217028912582 | 1.0 → 1.0 | True | same new observation / DIRECT | CONTINUATION_CANDIDATE | 2.5765299466159455 |
| PSA | 175621134.0 → 186843449.0 | 6.390070912536072 | 1.0 → 1.0 | True | same new observation / DIRECT | CONTINUATION_CANDIDATE | 4.025757519078477 |
| RTX | 1347758144.0 → 1349440548.0 | 0.12482981516304115 | 1.0 → NULL | True | same new observation / DIRECT | REVIEW_REQUIRED_FACTOR_CHANGE | NULL |
| T | 6852385650.0 → 6736473433.0 | -1.6915600335483116 | 1.0 → NULL | True | same new observation / DIRECT | REVIEW_REQUIRED_FACTOR_CHANGE | NULL |

The factor mismatch is the first differing **classification predicate**, not the only material difference in underlying evidence. GE/RTX/T also have a truncated source payload and missing valuation/equity inputs; the six normal cases retain full provider P/B inputs. Category/identity continuity and small share changes do not eliminate those differences. There is no reviewed percentage “safe band” that makes a missing raw factor identity-equivalent; existing continuation candidates still require operator confirmation even for large share changes.

## 7. Bounded prevalence and source clustering

Denominator 1: **nine OPEN ownership cases**. Exactly **3/9** have None; all three are 1.0 → None (GE, RTX, T). Six are 1.0 → 1.0. Other transitions: **0**. Affected companies/tickers: **3**. All three are unchanged NYSE Domestic Common Stock Primary Class securities.

Denominator 2: the exact historical 15-ticker `REFRESH_COPY_4d40fa311c02d4162e9c` batch. Thirteen tickers still retain ARQ rows from that run in the active provider DB; ADC and VRSN no longer have rows from that run. Taking **one latest surviving ARQ row per retained ticker**, **13/13** omit the factor key and the five P/B fields checked. These rows cluster by the same ingestion run/time and 29-key projection, across nine Domestic Common Stock and four Domestic Common Stock Primary Class metadata categories. This is not a provider-wide null rate or an all-history count. The 13 rows include 11 FY2026 Q3 rows, PENG FY2026 Q4 and XTIA FY2026 Q2.

| Latest retained batch ARQ ticker | Fiscal label | Observation ID | Factor key | Payload keys |
| --- | --- | --- | --- | --- |
| CLF | 2026-Q3 | 3db4b9f69bf38bbc62e0d6b4e3406eca4239094c9837e12b0a85262ca04bde50 | absent | 29 |
| EFX | 2026-Q3 | e2f4bf758e288ab5024e51e833272cdb315f2b20353a3812619c2e882a07d887 | absent | 29 |
| GE | 2026-Q3 | 5806bfc4a10a7d809ef83498c8360b26660ce28502d81408e7b189426a2cab24 | absent | 29 |
| GPC | 2026-Q3 | 04a4491bcaec23533506bfdb30aa33a9510c02f8c9f61074517cce1425bc3b50 | absent | 29 |
| IRDM | 2026-Q3 | 661d9762bb7cf996830374ac1c87fd04773bbda0bcec678249e36438d6a1adba | absent | 29 |
| NFLX | 2026-Q3 | 541a2057968eb7000d9b7ccbdfce0e5bf4940c4319bddcaebc89b2d7c8abe953 | absent | 29 |
| PEGA | 2026-Q3 | a5b185c5f7ba5da4f9806bbffbf53baa43685948acdc3fbc9d16e07422faf8dd | absent | 29 |
| PENG | 2026-Q4 | 638a5a8b477b029370eef97ea51efb8990e051086422d19508c8b2e2ab8df396 | absent | 29 |
| RTX | 2026-Q3 | bfd42bf2f633cfb8e511931673bc6769ea1bad22859c227d602d7328d42ea4f1 | absent | 29 |
| T | 2026-Q3 | a04ecf0968eaee10a2018c39e9d80057e59520770412d784f518bdd0c3ad6e1c | absent | 29 |
| UAL | 2026-Q3 | b9e9771aeb5b10de9c6ce7e82894792efbb32039eb0bea56158cd3902edd00eb | absent | 29 |
| URI | 2026-Q3 | 3a507fbd2c5233ca9b30f78772bce7a113a78511d2df8022aea10d05b1365f22 | absent | 29 |
| XTIA | 2026-Q2 | 45d8f40d83891f68a1820b258e7dfe4b667e06eeae3d342469157698f9028141 | absent | 29 |

This independent source cohort supports a storage-route pattern, rather than a coordinated identity-factor change in three companies. It does not certify the original upstream Q3 factor for any row.

## 8. Internal corporate-action cross-check and identity

No internal provider action with ticker or contraticker GE/RTX/T, no local split, and no retained review known_share_changes entry was found from each prior provider date through 2026-10-28. The bounded transition windows begin GE 2026-07-16, RTX 2026-07-23 and T 2026-07-22. No internal evidence links the omissions to a split/reverse split, share-class conversion, spin-off, merger, unusual issuance or provider-adjustment event.

Coverage limits matter: sharadar_action_metadata has 156 rows, latest event 2026-08-31, fetched 2026-08-31T06:24:31Z. It is a stale filtered bootstrap, not complete quarter-transition coverage. Local split evidence has maximum split date 2026-10-27 and latest creation 2026-10-28, but is not a complete issuance/class/merger ledger. Therefore **ABSENT in the queried internal evidence** does not establish that no corporate action occurred. No web research was performed.

| Case | Exact issuer/security binding | Provider stable key old metadata → current mapping | Category / exchange continuity | Active classes | Internal action/split evidence in window |
| --- | --- | --- | --- | --- | --- |
| GE | PASS | 199688 → 199688 | Domestic Common Stock Primary Class / NYSE unchanged | 1 | ABSENT |
| RTX | PASS | 199251 → 199251 | Domestic Common Stock Primary Class / NYSE unchanged | 1 | ABSENT |
| T | PASS | 198738 → 198738 | Domestic Common Stock Primary Class / NYSE unchanged | 1 | ABSENT |

Current and October 8 archived SF1 metadata rows are exactly equal as parsed dictionaries for each company. Canonical company key/security/ticker bindings equal the prior reviewed binding; one active security is returned. Permatickers are GE 199688, RTX 199251 and T 198738. The old raw financial payloads/native rows omit permaticker/provider-security ID, so stable identity is established through the archived/current metadata and canonical provider identity mapping, not by inventing a missing raw field. Canonical provider-company identity and provider-security identity rows were captured read-only. No generic listing-class inference replaces the reviewed ordinary interpretation.

## 9. Primary root cause and current-code status

| Case | Stored-null origin | Exactly one primary root class | Basis |
| --- | --- | --- | --- |
| GE | NORMALIZATION_REMOVED_VALUE in legacy ingestion | INGESTION_FACTOR_LOSS | 8 exact historical full→projection matches; same 29-key current Q3 shape/run; no identity/action basis for equivalence |
| RTX | NORMALIZATION_REMOVED_VALUE in legacy ingestion | INGESTION_FACTOR_LOSS | 8 exact historical full→projection matches; same 29-key current Q3 shape/run; no identity/action basis for equivalence |
| T | NORMALIZATION_REMOVED_VALUE in legacy ingestion | INGESTION_FACTOR_LOSS | 8 exact historical full→projection matches; same 29-key current Q3 shape/run; no identity/action basis for equivalence |

All three share one common root cause. BENIGN_PROVIDER_NULL_IDENTITY_FACTOR is not supported; RAW_PROVIDER_MISSING_UNKNOWN would wrongly omit the proven historical loss mechanism. There is no positive evidence of REAL_OWNERSHIP_BASIS_CHANGE or CORPORATE_ACTION_RELATED. Current Q3 wire-factor uncertainty remains an explicit limit of the ingestion-loss finding.

The generic raw-payload preservation fix is **already present** in commit `f23af13e7086296b1c917dcc5d2c25ca7accb3f6`: validate_complete_history retains `_acquisition_payload`, and replacement persists that full mapping when supplied. Pure replay of each archived exact source through today's validator preserves all 112 fields and its factor '1.0', whereas its 29-field financial normalizer still intentionally omits that field. Reimplementing that preservation change is unnecessary. It does not retroactively reconstruct payloads already stored by the old route.

There is a separate repair-detection gap: the current raw/effective financial fingerprints exclude the P/B extras. Pure helper checks show that removing sharefactor, equity/equityusd, price, marketcap and pb from the archived row leaves those semantic fingerprints unchanged. compare_ticker_histories compares those projections; a completeness-only improvement need not become a replacement-class change. An unchanged financial history or a ticker absent from the discovery window therefore cannot be relied on to repair old missing payload fields automatically. This is why the future implementation recommendation addresses explicit completeness/repair detection, while leaving factor equivalence and ownership approval unchanged.

## 10. Safe future policy alternatives

| Option | Evaluation | Disposition |
| --- | --- | --- |
| 1 — strict old != new → review | Preserves exact evidence binding and detects the observed loss. The hold is appropriate even though it is not evidence of a real ownership change. | RECOMMENDED now; retain fail closed. |
| 2 — conditional identity-null equivalence | Current raw stored absence is caused by a lossy projection; true upstream absence is not proved. Current candidate P/B cannot reconstruct; no reviewed safe band exists; action coverage is incomplete. | Do not permit these cases or auto-continue on those checks alone. |
| 3 — source-normalized identity default | No inspected source contract states missing sharefactor means one. Historical same-key payloads demonstrably had a value before storage dropped it. | Reject None→1 normalization without separately proven source-specific contractual semantics. |
| 4 — remove factor from blocking | Raw factor is not the ordinary multiplier, but it participates in binding, generic eligibility and review/candidate eligibility; ADS interpretations have separate economic ratios. | Reject generic removal; it would hide data-integrity loss. |

Recommended policy: distinguish known source-field loss from a genuine provider value change diagnostically, while keeping both noncontinuable until complete observation-bound evidence is reviewed. Recover complete current source evidence through a separately authorized repair workflow; do not carry forward a prior factor, use old equity, infer ratios from marketcap/P/B, or treat absence of internal corporate actions as proof of identity. A new explicit ownership review can be considered only after source completeness and the existing gates are satisfied. Missing-factor cases remain manual/held; this audit establishes no safe automatic equivalence conditions.

## 11. Auto-continuation implication and approval safety

For the existing **P/B ownership auto-continuation policy backlog**, 1.0 → None must remain **excluded from automatic continuation**, not converted to a nonblocking warning. A data-loss anomaly is not a validated ownership continuation. Future automation must reject incomplete/truncated source payloads and preserve exact raw-factor evidence. Repaired observations would need fresh observation/hash-bound review; there is no transfer of approval by ticker or small share delta.

| Case | Current manual continuation safety | UI continuation action | Reason |
| --- | --- | --- | --- |
| GE | NOT_SAFE_TO_APPROVE | disabled | Unknown Q3 factor after field loss; equity/native capitalization evidence also absent; full continuation cannot be validated |
| RTX | NOT_SAFE_TO_APPROVE | disabled | Unknown Q3 factor after field loss; equity/native capitalization evidence also absent; full continuation cannot be validated |
| T | NOT_SAFE_TO_APPROVE | disabled | Unknown Q3 factor after field loss; equity/native capitalization evidence also absent; full continuation cannot be validated |

These are recommendations on the current evidence, not review decisions. The cases remain OPEN. Current UI gating and backend classification rejection are separate from the economic assessment; a hypothetical exact None record in a pure helper is not an approval route. Source completeness repair does not itself authorize ownership continuation or Production publication.

## 12. UI implications and lightweight review UX backlog

**UI context sufficient: NO.** The queue currently shows old/new raw factors, categories, share delta, classification/status and current_pb_status. It does not distinguish an absent stored key from an upstream null, reveal the legacy ingestion origin, explain that the ordinary multiplier is independently reviewed, expose the correlated equity/price/cap omissions, or summarize exact identity continuity and the limitations of internal action evidence. The generic queue current_pb_status can also differ from the fresh first failing reason MISSING_EQUITY.

Record for the existing lightweight-review UX backlog: show source observation/hash/origin and factor-key presence; raw versus normalized factor; actual economic-unit rule; a source-completeness diagnostic; identity/category continuity; actual fresh P/B gate reason; and action-evidence result with its coverage dates. Preserve the disabled continuation action for unresolved factor/completeness anomalies. This is documentation only, not a second recommended implementation phase or a change to optional operator/note, factor-null policy or auto-continuation.

## 13. Validation and runtime invariance

No pytest/full suite or writer tests were run. Read-only SQL and pure helpers established nine fresh exact candidate fingerprints, three focus cases, 24 same-key normalized payload/hash matches, three current validator full-payload-preservation checks, three P/B-field completeness-fingerprint checks and the isolated ordinary None/one binding/capitalization comparisons. Existing directly relevant classification/quarterly ownership tests were inspected only; their writer paths were not invoked.

All live inputs were opened read-only; SQL query_only was set on audit connections. Existing ownership preview itself uses mode=ro; no Refresh Preview/Test/Production or publication workflow ran. Before/after hashing used existing UI-operation, Production and scheduler kernel lock files through read-only handles without rewriting lock-owner data. Nine runtime files, the exact watermark row, all nine complete ownership rows and all ten ownership audit events are unchanged. Source and bundled ownership-artifact hashes are unchanged. The archived provider DB was also hashed before/after. No DB/schema/table, queue, scheduler, manifest, watermark, journal, decision, evidence export, inactive candidate or registry was mutated. Existing unrelated worktree changes are preserved.

| Protected runtime artifact | Identical before/after SHA-256 |
| --- | --- |
| active_manifest | 4ed37754c69b475bb0341eb85fd24581a49a63049f03487045f6a1da99a54198 |
| analysis | ce5a09a8782660703e5160aa44a798ea2029318732466f0aa90b28c38321e3e8 |
| canonical | 11ad0c3106a80bd8583a317f595e5d21f49a5431ec9dfc99fc4db8bb7eccd35e |
| generation_manifest | 4ed37754c69b475bb0341eb85fd24581a49a63049f03487045f6a1da99a54198 |
| journal | 8c88e3894b9376be4b56cc51041274d7ca368967e87dbf532f5c491e54190eae |
| market | 0dd3a0fe6d4de465a075e7771128d11b370f3159b26a27c9d05d810fb360832f |
| provider | 6d0262597c4248d40ce8b7ac79b164b1f8fcdfc09fa72283e35486d94380ae81 |
| queue | 746836b89c2bc2bcf5880812bdcdd64024c2c4398e196e21746b74fbf0f68b99 |
| scheduler_config | 3a0b74412a0fb9cf5e7a9b370e97a6d48af031d5094d53b5689669e630c9e894 |

Retained October 8 provider DB SHA-256: `2b3a57add8b51413d98f220d4cdd313994d1a4079f987a94796bf6a2b6db5fbb`. Full provider/canonical/analysis hashes and active-path equality protect the accepted generation, while the explicit `sharadar_refresh_state` comparison protects watermark **2026-10-27** and its run/time fields.

Evidence remains outside Git under `/tmp/pb_ownership_provider_factor_null_audit`:

| Temporary artifact | SHA-256 |
| --- | --- |
| before.json | e4f22a4680173d22318ab8849a3ef746e8d146b6cc4e295ebd83cb47e31870be |
| initial.json | 8a523489a3fb679ca0d76f36b113a650a8a04046b0a679f11b5b22701774b959 |
| archives.json | c8defa35297e0a227436de6ab48f915cc453b276b5a79c67ce440515794f31ba |
| audit.json | 903ea13d325a5660a5c74c6282562758421a9f83295e3b227e20403aaa588cf1 |
| completeness_gap.json | 47668f090e4173b3fb681d9eb5c84dd583daae43264bafa4adf2606fef557bff |
| cohort_metadata.json | af8dce5632342ae8c9a64584fb34a64ca1db849a59201ac1b06b859967bab24b |
| verification.json | b0319b3616d0f0eb15588fef8326e280afe2607a7b2cbd64c3b83a8e795f242e |

| Historical source artifact inspected, not committed | SHA-256 |
| --- | --- |
| fundamental_reports/admin_runs/20261022T043408Z_refresh_fundamentals_bb23ca223d59_production_eb6f648d/source_revalidation.json | 2f947fbcd983cf305741af9d36c389ecd1b38b3594c9b131a97890df30aa4f06 |
| fundamental_reports/admin_runs/20261022T042658Z_refresh_fundamentals_bb23ca223d59_test/provider_replacement_summary.json | f538996eb0a8283c0fa646018aae13486da47e6eb927b4ba4c4c89274bd1b5dc |

## 14. Exactly one bounded next implementation phase

**P/B-PROVIDER-PAYLOAD-COMPLETENESS-REPAIR-1 — detect and rehearse repair of legacy financial-projection payloads without relaxing ownership policy.** Add an explicit, separately bound payload-completeness comparison so a full source observation can repair a legacy projected payload even when financial semantic fingerprints are unchanged. Retain the existing full-acquisition preservation path; distinguish absent keys, true source nulls and valid values. Use GE/RTX/T's exact legacy shapes and 24 historical full-source pairs as focused regression evidence. Require exact source-key/identity binding, complete current source evidence and copy-only rehearsal before any separately authorized live repair. Do not fabricate Q3 factors/equity from the archive, silently rewrite immutable evidence, alter P/B arithmetic/factor semantics, auto-approve, change auto-continuation policy or publish. Preserve established fiscal-identity and reviewed-source contracts. Current source data and decisions remain untouched by this audit.

Commit only this audit documentation. No source, tests, databases, raw payloads, runtime artifacts, manifests, journal, queue, logs, helper scripts or unrelated worktree changes are included. No push.
