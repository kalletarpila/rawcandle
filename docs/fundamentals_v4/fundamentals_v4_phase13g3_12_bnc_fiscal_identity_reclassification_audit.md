# Phase 13G.3.12 BNC Fiscal-Identity Reclassification Audit

## 1. Purpose

Audit, without production writes, the BNC ARQ same-key fiscal reclassification from `2026-Q1` to `2026-Q4` and decide whether the first Refresh Production may proceed. Fiscal identity is evaluated from source and filing metadata. BNC's exceptional FY2026 strategic, accounting, predecessor/successor, and financial structural break makes quarter-to-quarter financial continuity unsuitable as fiscal-identity evidence.

## 2. Accepted Preview/Test Basis

The accepted evidence chain is Preview `20260920T122311Z_refresh_fundamentals_81d416e6f45b` and copy-only Test `20260920T122417Z_refresh_fundamentals_eaf4b9d9de09_test`. The Test was technically successful but remained blocked by the BNC removal. This audit reused its durable evidence and made one read-only complete-history Sharadar acquisition for all 71 changed known tickers. No Preview, Test, full workflow, scheduler Preview, or Production was run.

## 3. BNC Source-Key Transition

The true source key remained exactly `(BNC, ARQ, 2026-06-23, 2026-04-30)`. Production provider state mapped it to `2026-Q1`; current Sharadar maps it to `2026-Q4`. The old normalized row fingerprint is `00b0ab1695479f3df0c9269a671d6611766e213a167257c5eacb9356ba57a273`; the current fingerprint is `69beaba0dc9e8f6dad8c1ab3ee2eba9ea2e56b8d21cfc72eacc50d02f8358502`. `lastupdated` changed from `2026-06-23` to `2026-09-14`, while `calendardate` remained `2026-03-31`.

The financial payload also changed materially: revenue, gross profit, operating income, EBIT, net income, common net income, and weighted basic/diluted shares changed. The old/new financial fingerprints are `ebe0aa14fcdef2493472510fe3ab0b72cad7642dfb83f9537b039b1d78cdde2e` and `4a676d1f1d046a9f5a063ff2b5b22d4876abaa7b13ae857cd86eb15c833afd53`. Those changes are recorded as facts only. They are not used to infer fiscal identity because of BNC's FY2026 structural break.

## 4. Old Fiscal Sequence

| Dim. | Source date / reportperiod | Previous fiscal identity / lastupdated | Current fiscal identity / lastupdated | True-key status | Same fiscal identity elsewhere? |
| --- | --- | --- | --- | --- | --- |
| ARQ | 2025-05-15 / 2025-03-31 | 2025 Q1 / 2026-06-23 | 2025 Q1 / 2026-06-23 | unchanged | ARQ 2025-04-30 also Q1 |
| ARQ | 2025-07-25 / 2025-04-30 | 2025 Q1 / 2026-06-23 | 2025 Q1 / 2026-06-23 | unchanged | yes |
| ARQ | 2025-09-22 / 2025-07-31 | 2025 Q2 / 2026-06-23 | 2025 Q2 / 2026-06-23 | unchanged | no |
| ARQ | 2025-12-15 / 2025-10-31 | 2025 Q3 / 2026-06-23 | 2025 Q3 / 2026-09-14 | unchanged; content revised | no |
| ARQ | 2026-03-16 / 2026-01-31 | 2026 Q4 / 2026-06-23 | 2026 Q4 / 2026-06-23 | unchanged | affected row also Q4 |
| ARQ | 2026-06-23 / 2026-04-30 | **2026 Q1 / 2026-06-23** | **2026 Q4 / 2026-09-14** | **unchanged; identity and content revised** | target Q4 already exists |
| ARQ | 2026-09-11 / 2026-07-31 | absent | 2027 Q1 / 2026-09-14 | new key | MRQ also 2027 Q1 |
| MRQ | 2025-04-30 / 2025-04-30 | 2025 Q4 / 2026-06-23 | 2025 Q4 / 2026-09-14 | unchanged; content revised | older MRQ 2025-01-31 also Q4 |
| MRQ | 2025-07-31 / 2025-07-31 | 2026 Q1 / 2026-06-23 | 2026 Q1 / 2026-06-23 | unchanged | no |
| MRQ | 2025-10-31 / 2025-10-31 | 2026 Q2 / 2026-06-23 | 2026 Q2 / 2026-09-14 | unchanged; content revised | no |
| MRQ | 2026-01-31 / 2026-01-31 | 2026 Q3 / 2026-06-23 | 2026 Q3 / 2026-06-23 | unchanged | no |
| MRQ | 2026-04-30 / 2026-04-30 | 2026 Q4 / 2026-06-23 | 2026 Q4 / 2026-09-14 | unchanged; content revised | ARQ affected row also Q4 |
| MRQ | 2026-07-31 / 2026-07-31 | absent | 2027 Q1 / 2026-09-14 | new key | ARQ also 2027 Q1 |

All rows include the true source identity `(ticker, dimension, date, reportperiod)` through the ticker context and the dimension/date/reportperiod columns. Their `calendardate` values run `2025-03-31`, `2025-03-31`, `2025-06-30`, `2025-09-30`, `2025-12-31`, `2026-03-31`, and `2026-06-30` in the displayed ARQ order; MRQ uses the same calendar anchors for corresponding reportperiods. The complete current source has only one period after the affected key, so no additional four-quarter future history exists to inspect.

The old ARQ progression ended `2025 Q3 -> 2026 Q4 -> 2026 Q1`, an order reversal. It also disagreed with the old MRQ identity for reportperiod `2026-04-30`, which was already `2026-Q4`. The old sequence is not valid.

## 5. Current Fiscal Sequence

Current ARQ changes the affected row to Q4 and then proceeds to 2027 Q1. That removes the Q4-to-Q1 reversal, but it leaves two ARQ reportperiods assigned to stable identity `2026 Q4`: `2026-01-31` and `2026-04-30`. The current source therefore remains invalid as a unique stable-quarter sequence.

Current MRQ around the boundary is coherent: `2025-07-31 -> 2026 Q1`, `2025-10-31 -> 2026 Q2`, `2026-01-31 -> 2026 Q3`, `2026-04-30 -> 2026 Q4`, and `2026-07-31 -> 2027 Q1`. Assigning `2026-04-30` to 2026 Q4 is clearly more coherent than the former Q1 assignment, but it does not cure Sharadar ARQ's separate erroneous Q4 assignment for `2026-01-31`.

## 6. ARQ/MRQ Agreement

For reportperiod `2026-04-30`, current ARQ (`date=2026-06-23`) and MRQ (`date=2026-04-30`) both say `2026-Q4`. Previously ARQ said Q1 while MRQ said Q4. They now agree on the affected period and share reportperiod, but not source date.

The neighboring `2026-01-31` reportperiod still contradicts: ARQ says `2026-Q4`, while MRQ says `2026-Q3`. Thus affected-period agreement is strong evidence for the Q1-to-Q4 correction, but the complete current ARQ/MRQ source contract remains contradictory.

## 7. Official Fiscal Calendar Evidence

The [SEC 2026 10-K filing index](https://www.sec.gov/Archives/edgar/data/1482541/000148254126000019/0001482541-26-000019-index.htm) records filing date `2026-06-23`, period of report `2026-04-30`, and fiscal year end `0430`. The [annual report](https://www.sec.gov/Archives/edgar/data/1482541/000148254126000019/bncww-20260430.htm) identifies the fiscal year ended April 30, 2026, and the [company results release filed with the SEC](https://www.sec.gov/Archives/edgar/data/1482541/000148254126000021/bnc-2026x06x22xpr.htm) calls it the fourth quarter and full fiscal year.

The [January 31, 2026 10-Q](https://www.sec.gov/Archives/edgar/data/1482541/000149315226010296/form10-q.htm) reports the nine-month period in a company with an April 30 fiscal year end, making it FY2026 Q3. The [July 31, 2026 10-Q filing index](https://www.sec.gov/Archives/edgar/data/1482541/000148254126000051/0001482541-26-000051-index.htm) retains fiscal year end `0430`, consistent with FY2027 Q1. Official filing evidence therefore supports April 30 as FY2026 Q4 and contradicts Sharadar ARQ's January 31 `2026-Q4` label.

## 8. RawCandle Normalization Audit

RawCandle parses and validates source `fiscalperiod`, then derives normalized fiscal year/quarter directly from that value. It independently parses `date`, `reportperiod`, `calendardate`, and `lastupdated`; it does not derive fiscal identity from their calendar years or from financial continuity. The Q1-to-Q4 value is present in the current authoritative Sharadar response. This is a provider metadata issue, not a RawCandle normalization defect.

Sharadar semantics used here are: `date` is source availability/filing date, `reportperiod` is the statement period end, `calendardate` is a standardized calendar anchor, and `fiscalperiod` is the provider's fiscal identity authority. RawCandle's mapping preserves those roles.

## 9. Other Fiscal-Identity Revisions

The read-only comparison covered complete current ARQ/MRQ histories for all 71 changed known tickers from the accepted Refresh set. Exactly one same-true-key fiscal-identity revision exists: BNC ARQ. Counts are: total `1`, affected tickers `1`, ARQ `1`, MRQ `0`, prior stable identities removed `1`, target stable identities newly created by revision `0`, and moves into an already existing stable identity `1`. BNC is the only canonical-removal case.

The Test's BNC canonical `+1` is the independent new source period `2026-07-31 -> 2027 Q1`; it is not created by the Q1-to-Q4 revision. No non-BNC material example exists to deep-dive. The observed inconsistency is isolated to BNC in this 71-ticker set and is not evidence of a broader normalization failure.

## 10. BNC Canonical Impact

The Test candidate reports BNC `+1 / 2 / -1`. If the source were accepted, the correct causal chain would be: same true source key changes stable fiscal identity -> no accepted ARQ winner remains for old `2026 Q1` -> old canonical `2026 Q1` is removed -> canonical state is rebuilt from current ARQ winners. This is not a true source-key removal.

The current builder selects the newer April 30 ARQ row as the existing 2026 Q4 winner and removes Q1. Because the complete ARQ history contains a duplicate Q4 and contradicts SEC/MRQ for January 31, that result must not be published under the current evidence.

## 11. first_public_result_date Impact

Old canonical `2026 Q1` has `first_public_result_date=2026-06-23`. Existing canonical `2026 Q4` has `first_public_result_date=2026-03-16`, based on the January 31 ARQ row. The Test candidate makes the April 30 row the Q4 winner, changes Q4 `source_availability_date` to `2026-06-23`, and preserves Q4 `first_public_result_date=2026-03-16` by stable identity.

The removed Q1 date must remain only in deletion/reclassification evidence and must never be copied mechanically to an existing Q4. For a valid revision into an independently valid existing target, preserve the target's established date. For a genuinely new stable identity, initialize from the accepted winner under the canonical publication-date policy. Here the target identity's prior basis is itself contradicted by SEC/MRQ, so neither date should be blessed before resolving BNC.

## 12. Fiscal Identity Revision vs Source Removal

`TRUE_SOURCE_REMOVAL` means the authoritative complete source no longer contains a true key. `FISCAL_IDENTITY_REVISION` means the same true key remains but its source fiscal metadata maps it to another stable quarter. BNC is the latter. Reporting it as removal would lose the cause and misstate source evidence.

The generic report should eventually expose `FISCAL_IDENTITY_REVISION` / `Fiscal quarter reclassification`, separately from true removal, financial historical revision, and source-window retention. This audit does not implement that contract.

## 13. Historical Research Implications

Keeping old Q1 after a valid source correction can duplicate the same economics across Q1/Q4 and contradict current authoritative chronology. Accepting a demonstrably corrected identity fits RawCandle's current-state, rebuildable architecture. Preserving both versions would require a permanent PIT/version subsystem that is outside the architecture and is not justified here; durable audit and rollback evidence is sufficient.

BNC is not strategically important to this universe. Since its structurally abnormal source history cannot currently satisfy the generic fiscal-identity contract, ticker-specific winner logic is not justified. Controlled removal of BNC from the Fundamentals universe is preferable to special-case code, after the removal's normal downstream effects are audited in a separately authorized phase.

## 14. Proposed Generic Policy

Model same-key fiscal remaps explicitly as `FISCAL_IDENTITY_REVISION`. Auto-accept only when the complete source is trusted, ARQ/MRQ and official evidence agree, the resulting sequence is unique and ordered, no duplicate stable identity is created, and normalization is proven innocent. Otherwise emit `REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION` and block candidate publication.

The policy must be generic and fail closed. It must not include BNC-specific branches. In this isolated case, the operational resolution should be controlled BNC universe removal rather than architectural complexity solely to retain it.

## 15. Production Gate Decision

`SOURCE_OR_NORMALIZATION_DEFECT`

More precisely, this is a BNC-specific current-source defect: April 30 Q4 is supported, but current Sharadar ARQ also labels January 31 Q4, creating a duplicate stable identity contradicted by SEC and MRQ. RawCandle normalization is not the cause. The existing Preview/Test cannot authorize Production.

## 16. Need for Code Change

Outcome 3: domain/source handling requires a separate decision and implementation before Production. No runtime code changed in this audit. The next narrow phase should remove BNC from the Fundamentals universe through the established universe contract, or obtain corrected provider history, and should add only the smallest generic fail-closed detection/reporting needed for duplicate or contradictory fiscal identities. It must not add ticker-specific production logic.

Any change to universe, Preview classification, validation, or candidate semantics makes the accepted chain stale. A fresh Preview and Test are required afterward.

## 17. Production Safety

Before and after the read-only audit, production state is unchanged:

| Role | SHA-256 | Size | mtime_ns |
| --- | --- | ---: | ---: |
| provider | `b71dfbb0128a4e5404a18c608e31e16ec08c07b75bbe416e1a48a62112469468` | 958828544 | 1789831083995864659 |
| canonical | `bee62a677777be63ce67737d9e77d375f22dd044b6a7c9c834ccbe7b9f1684cf` | 655724544 | 1789893262044507282 |
| analysis | `969eb38504893b260206f07033a292b0587c16164720556f11d1b77e69b834f2` | 902062080 | 1789831394579542627 |

Refresh state remains `BOOTSTRAP_BASELINE`; no published watermark was created. No candidate DB, Test DB, production backup, publication journal, or large temporary database was created.

## 18. Next Step

Recommendation **C - More work required before Production**. Authorize a narrow controlled-universe-removal and generic validation/reporting phase for BNC, then establish a fresh Preview -> Test -> review chain. Do not run Refresh Production from the current chain.

## 19. Git

Baseline is `6b3f969 fix: close refresh test evidence gaps`. This phase adds only this audit report and its lightweight CSV. No push is performed.

Refresh Production was NOT executed.
