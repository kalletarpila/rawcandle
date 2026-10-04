# KO Raw ARQ/MRQ Followup

Date: 2026-10-04

## Prior Context and New Boundary

Followup to commit 7c43c496 and ko_retained_history_review_2026-10-04.md.
Exact old Preview: `20261004T132346Z_refresh_fundamentals_bee6f4d28686`.
Review item: `666db8590ea8f6cc8599ba837fc833d974d148b50ec952d5b2d3cd408c4f3311`.
The old NOT_SAFE decision was justified: source absence remained ambiguous and
the early held-ticker exit did not classify incoming financial revisions.

This fetch is a separate evidence boundary, not an approval or a new Preview.
Two production SharadarClient fundamentals requests, ticker=KO, dimensions ARQ/MRQ,
limit=10000, default production authentication, pacing and retry behavior.
Both returned COMPLETE below the request limit, with no validation errors.
No other tickers, discovery, refresh, approval, Test or Production operation ran.

Raw evidence: `/tmp/ko_arq_mrq_raw_2026-10-04.json` (temporary, not committed).
It includes redacted request identities, complete provider records, normalized rows,
row-level raw/effective hashes, retained observation provenance, exhaustive payload
diffs, canonical cash comparison and database pre/post fingerprints.
Raw/effective history hashes below are the established refresh contract projections,
not SHA-256 of all response bytes; extra provider fields are compared separately.
Full-record SHA-256 (source-key sorted rows, sorted JSON keys, compact separators):
ARQ `041aa071d33b32558bd4c3cf30960dce16bc0d05b2f3fcd44738399b1377505b`;
MRQ `d14f267fb1b2a48e38f3437d31fee8e49b35552dc19a7031ed7d4feb424dcaf1`.
These include every returned field; no equivalent full-record hash was retained
by the old Preview, so they are not retroactively compared to its projected hashes.

## Fresh Response and Exact Preview Comparison

| Dimension | Fetch UTC | Rows | Oldest reportperiod | Newest reportperiod |
|---|---|---:|---|---|
| ARQ | 2026-10-04T15:10:06.431066+00:00 | 40 | 2016-09-30 | 2026-07-03 |
| MRQ | 2026-10-04T15:10:06.882251+00:00 | 39 | 2016-12-31 | 2026-07-03 |

ARQ raw: `f435c36e0de4465d3dfd1a416b2dd2e11b6d82ce5a9d7bba2e59acccd5be4262`
ARQ effective: `6db386cf456425d918ee5f0b9172ac91587a37cbc36a2a748bf0f340e41df69c`

MRQ raw: `76266a0b7fb371f53af0349318212c07b8fa0e11f85923314ed275dc09590331`
MRQ effective: `d1a32c0f113d7070479884cb0dc822230361ffcca5f28f76a508698e3b3a4bf6`

Both counts, windows and BOTH raw/effective fingerprints exactly reproduce the old
Preview. No changed source state is detected within its fingerprinted field contract.
The old Preview did not retain complete rows: direct old-versus-new extra-field
comparison is impossible. Fingerprint equality is strong reproducibility evidence,
not byte-for-byte proof about unrecorded extra fields.

## Three Missing Rows

| Dimension / fiscal identity | date / reportperiod | Fresh state | Assessment |
|---|---|---|---|
| ARQ / 2016-Q2 | 2016-07-28 / 2016-07-01 | CURRENTLY_ABSENT | Prior proven normal aging; retain outside source window |
| MRQ / 2016-Q2 | 2016-07-01 / 2016-07-01 | CURRENTLY_ABSENT | Prior proven normal aging; retain outside source window |
| MRQ / 2016-Q3 | 2016-09-30 / 2016-09-30 | CURRENTLY_ABSENT | STILL_AMBIGUOUS |

Accepted history contains 41 rows per dimension. Fresh ARQ is missing exactly one
oldest key; MRQ exactly two. No new keys, changed dates/reportperiods, fiscal labels,
same-fiscal replacement keys or reclassification candidates exist. Shared rows:
40 ARQ and 39 MRQ changed payload; zero fully unchanged rows.

## Exact Fingerprint Mismatch Explanation

Every shared normalized row changed ONLY cashneq and lastupdated:
`lastupdated: 2026-07-29 -> 2026-10-03` for all 79 rows.
Cash is a financial change, not metadata. No other refresh projection field changes.
Removing the three keys, then applying exactly these 79 cash/lastupdated changes
reconstructs BOTH exact Preview raw/effective fingerprints independently: PASS.
Therefore the old unexplained mismatch is fully located within the hash contract.

Full provider payload comparison additionally finds cashnequsd, ev, evebitda, invcap,
investments and investmentsc changed in all 79 rows; evebit in 12 ARQ and 17 MRQ rows.
Numeric strings are compared with Decimal, empty/null treated as absent, avoiding
representation-only differences. Every value pair is listed in the appendix.
These extra financial/derived fields are outside the refresh fingerprint projection.
Cash reductions coincide with increases in investments/investmentsc; this supports
a cash-versus-investment provider classification revision, but is NOT proof of the
provider methodology or a reason for the missing MRQ row.

## MRQ 2016-Q3 Conclusion

`KO_Q3_MRQ_STILL_AMBIGUOUS`.
The omission is a coherent oldest prefix, not an interior hole, and has no replacement
or fiscal conflict. This supports truncation as a plausible explanation. However,
the boundary still spans 40 quarters against the reviewed minimum 41; repeated
absence and hash reproduction do not establish the upstream cause. Selective source
removal is not proven either: surrounding earlier accessible history is absent.
The broad cash revision does not reclassify the missing quarter identity.
Do not relabel this as confirmed truncation, confirmed removal, or fiscal revision.

## Canonical Impact

Read-only SQL checked every changed ARQ fiscal identity for company_id=1231:
40 unique canonical quarters, all SHARADAR_ARQ_PRIMARY, and every existing cash value
equals the accepted ARQ cashneq. Thus accepting incoming revisions would change
canonical cash in 40 quarters (2016-Q3 through 2026-Q2), with downstream analysis
rebuild implications. No fiscal identities, period ends or other mapped financial
fields change. MRQ revisions do not independently override ARQ-primary canonical cash.
lastupdated is provider metadata; extra raw financial/valuation fields are not mapped
into these canonical financial columns. No canonical values were applied.
The three absent keys are NOT authorization to delete accepted canonical quarters.

## External and SwingMaster Evidence

Prior official KO Q3 existence and revenue/gross-profit/operating-income corroboration
remain valid; those fields did not change. No new external official fetch was needed.
SwingMaster V3 was not inspected: no reviewed path is available in the task or scoped
configuration, and its location was requested from the operator. This is an explicit
remaining evidence gap; no broad filesystem/repository discovery was performed.

## Review Item and Next Operator Step

Old NOT_SAFE remains correct. New evidence was not attached to or approved against
the old item. Existing queue remains unchanged. Even exact fingerprint reproduction
does not supply the missing provider-window proof.
`FRESH_PREVIEW_CAN_BE_EXPECTED_TO_ACCEPT_RETAINED_HISTORY`: NO on available evidence.
A fresh normal Preview would be expected to retain the KO hold while the same source
boundary persists. Do not execute acceptance solely because the API reports COMPLETE.
Next: provide the SwingMaster V3 data path for KO-only read-only provenance review;
if it cannot establish source-window semantics, obtain explicit Sharadar KO/MRQ window
or removal evidence. Only after that review run a fresh normal Preview and bind any
later approval to its exact evidence under the existing queue contract.

## Safety and Verification

No source code changes; no pytest required or run. Runtime assertions passed for
exact old Preview count/window/hash reproduction, reconstruction from retained rows
plus located changes, 40-quarter canonical cash parity, and unchanged DB hashes.
No publication, scheduler/systemd, provider/canonical/analysis/forecast/queue writes.
Active generation did not change during the read-only probe.

| Role | Pre SHA-256 = post SHA-256 |
|---|---|
| provider | `5192c9c7d2020b9897a39ab06c864fb9e35e3696e956de26f7ee52de37cd3270` |
| canonical | `765a5efdc601dc99c6969ef0e3fe80c2206472b91437486cf5b6b73fa8370a89` |
| analysis | `6c1487278f25eb118ecfb4312966ba65b8a241ff0d20694d698f097e06c95b23` |
| forecasts | `5cc1b771ecfab2e1e31e5d2d55f6947b8c26a54b7d381e8d90f230df16f32aec` |
| queue | `d7322ec86b5fe6a8ce9ccfc6f3f90127738f6fe82007e056e0f6c02cc052b914` |

## Exhaustive Row-Level Appendix

All rows below have ticker KO; source key is (KO, dimension, date, reportperiod).
Fiscal identity is unchanged. All deltas are financial/derived except lastupdated
(metadata); no source-key-only or fiscal-identity changes. Retained and incoming
values are provider-native units; all lastupdated values changed as stated above.
Unlisted fields are numerically/textually unchanged. The table also includes extra
provider fields excluded from the hash contract, not merely canonical mapped cash.

| Dimension | Date | Reportperiod | Fiscal identity | Exact field changes (retained -> incoming) |
|---|---|---|---|---|
| ARQ | 2016-10-27 | 2016-09-30 | 2016-Q3 | cashneq: 22412000000 -> 11147000000; cashnequsd: 22412000000 -> 11147000000; ev: 206473850602 -> 217738850602; evebit: 21 -> 22; evebitda: 17.781 -> 18.751; invcap: 68701000000 -> 79966000000; investments: 21184000000 -> 32449000000; investmentsc: 3157000000 -> 14422000000 |
| ARQ | 2017-02-24 | 2016-12-31 | 2016-Q4 | cashneq: 18150000000 -> 8555000000; cashnequsd: 18150000000 -> 8555000000; ev: 206939829910 -> 216534829910; evebit: 23 -> 24; evebitda: 19.462 -> 20.364; invcap: 67169000000 -> 76764000000; investments: 21300000000 -> 30895000000; investmentsc: 4051000000 -> 13646000000 |
| ARQ | 2017-04-27 | 2017-03-31 | 2017-Q1 | cashneq: 21911000000 -> 12120000000; cashnequsd: 21911000000 -> 12120000000; ev: 209300774246 -> 219091774246; evebit: 25 -> 26; evebitda: 20.57 -> 21.532; invcap: 69316000000 -> 79107000000; investments: 21277000000 -> 31068000000; investmentsc: 3294000000 -> 13085000000 |
| ARQ | 2017-07-27 | 2017-06-30 | 2017-Q2 | cashneq: 22734000000 -> 11718000000; cashnequsd: 22734000000 -> 11718000000; ev: 223619828828 -> 234635828828; evebit: 32 -> 34; evebitda: 26.508 -> 27.814; invcap: 72028000000 -> 83044000000; investments: 26493000000 -> 37509000000; investmentsc: 4490000000 -> 15506000000 |
| ARQ | 2017-10-26 | 2017-09-29 | 2017-Q3 | cashneq: 22219000000 -> 12528000000; cashnequsd: 22219000000 -> 12528000000; ev: 223851650019 -> 233542650019; evebit: 31 -> 32; evebitda: 26.053 -> 27.181; invcap: 73199000000 -> 82890000000; investments: 27899000000 -> 37590000000; investmentsc: 5138000000 -> 14829000000 |
| ARQ | 2018-02-23 | 2017-12-31 | 2017-Q4 | cashneq: 15358000000 -> 6006000000; cashnequsd: 15358000000 -> 6006000000; ev: 220197523713 -> 229549523713; evebit: 29 -> 30; evebitda: 24.716 -> 25.766; invcap: 76393000000 -> 85745000000; investments: 27269000000 -> 36621000000; investmentsc: 5317000000 -> 14669000000 |
| ARQ | 2018-05-01 | 2018-03-30 | 2018-Q1 | cashneq: 15809000000 -> 8291000000; cashnequsd: 15809000000 -> 8291000000; ev: 214369634304 -> 221887634304; evebit: 27 -> 28; evebitda: 23.155 -> 23.967; invcap: 77920000000 -> 85438000000; investments: 28081000000 -> 35599000000; investmentsc: 5564000000 -> 13082000000 |
| ARQ | 2018-07-26 | 2018-06-29 | 2018-Q2 | cashneq: 13818000000 -> 7975000000; cashnequsd: 13818000000 -> 7975000000; ev: 229638133949 -> 235481133949; evebit: 27 -> 28; evebitda: 24.079 -> 24.691; invcap: 74316000000 -> 80159000000; investments: 27155000000 -> 32998000000; investmentsc: 5536000000 -> 11379000000 |
| ARQ | 2018-10-30 | 2018-09-28 | 2018-Q3 | cashneq: 13792000000 -> 9065000000; cashnequsd: 13792000000 -> 9065000000; ev: 233782756962 -> 238509756962; evebitda: 22.868 -> 23.331; invcap: 69637000000 -> 74364000000; investments: 27005000000 -> 31732000000; investmentsc: 5055000000 -> 9782000000 |
| ARQ | 2019-02-21 | 2018-12-31 | 2018-Q4 | cashneq: 10951000000 -> 8926000000; cashnequsd: 10951000000 -> 8926000000; ev: 228671093822 -> 230696093822; evebit: 25 -> 26; evebitda: 22.726 -> 22.927; invcap: 69327000000 -> 71352000000; investments: 25287000000 -> 27312000000; investmentsc: 5013000000 -> 7038000000 |
| ARQ | 2019-04-25 | 2019-03-29 | 2019-Q1 | cashneq: 7183000000 -> 5645000000; cashnequsd: 7183000000 -> 5645000000; ev: 241174946910 -> 242712946910; evebitda: 23.282 -> 23.43; invcap: 74744000000 -> 76282000000; investments: 24963000000 -> 26501000000; investmentsc: 4765000000 -> 6303000000 |
| ARQ | 2019-07-25 | 2019-06-28 | 2019-Q2 | cashneq: 9303000000 -> 6731000000; cashnequsd: 9303000000 -> 6731000000; ev: 262700776082 -> 265272776082; evebitda: 24.981 -> 25.226; invcap: 69471000000 -> 72043000000; investments: 24370000000 -> 26942000000; investmentsc: 4058000000 -> 6630000000 |
| ARQ | 2019-10-24 | 2019-09-27 | 2019-Q3 | cashneq: 9532000000 -> 7531000000; cashnequsd: 9532000000 -> 7531000000; ev: 266920074098 -> 268921074098; evebit: 26 -> 27; evebitda: 23.544 -> 23.721; invcap: 68947000000 -> 70948000000; investments: 23023000000 -> 25024000000; investmentsc: 3456000000 -> 5457000000 |
| ARQ | 2020-02-24 | 2019-12-31 | 2019-Q4 | cashneq: 7947000000 -> 6480000000; cashnequsd: 7947000000 -> 6480000000; ev: 286440691330 -> 287907691330; evebitda: 21.98 -> 22.092; invcap: 67458000000 -> 68925000000; investments: 23107000000 -> 24574000000; investmentsc: 3228000000 -> 4695000000 |
| ARQ | 2020-04-24 | 2020-03-27 | 2020-Q1 | cashneq: 15274000000 -> 13561000000; cashnequsd: 15274000000 -> 13561000000; ev: 230235914167 -> 231948914167; evebitda: 16.609 -> 16.733; invcap: 68897000000 -> 70610000000; investments: 21064000000 -> 22777000000; investmentsc: 2392000000 -> 4105000000 |
| ARQ | 2020-07-22 | 2020-06-26 | 2020-Q2 | cashneq: 17588000000 -> 10037000000; cashnequsd: 17588000000 -> 10037000000; ev: 242987878793 -> 250538878793; evebit: 21 -> 22; evebitda: 18.488 -> 19.063; invcap: 75139000000 -> 82690000000; investments: 21163000000 -> 28714000000; investmentsc: 2228000000 -> 9779000000 |
| ARQ | 2020-10-22 | 2020-09-25 | 2020-Q3 | cashneq: 18732000000 -> 11385000000; cashnequsd: 18732000000 -> 11385000000; ev: 251928986136 -> 259275986136; evebitda: 19.915 -> 20.496; invcap: 76508000000 -> 83855000000; investments: 21983000000 -> 29330000000; investmentsc: 2396000000 -> 9743000000 |
| ARQ | 2021-02-25 | 2020-12-31 | 2020-Q4 | cashneq: 8566000000 -> 6795000000; cashnequsd: 8566000000 -> 6795000000; ev: 250425166785 -> 252196166785; evebit: 22 -> 23; evebitda: 19.717 -> 19.856; invcap: 78372000000 -> 80143000000; investments: 22433000000 -> 24204000000; investmentsc: 2348000000 -> 4119000000 |
| ARQ | 2021-04-27 | 2021-04-02 | 2021-Q1 | cashneq: 10355000000 -> 8484000000; cashnequsd: 10355000000 -> 8484000000; ev: 265647850138 -> 267518850138; evebitda: 20.897 -> 21.045; invcap: 79345000000 -> 81216000000; investments: 22006000000 -> 23877000000; investmentsc: 2234000000 -> 4105000000 |
| ARQ | 2021-07-26 | 2021-07-02 | 2021-Q2 | cashneq: 11267000000 -> 9188000000; cashnequsd: 11267000000 -> 9188000000; ev: 277047263193 -> 279126263193; evebitda: 18.927 -> 19.069; invcap: 76730000000 -> 78809000000; investments: 21191000000 -> 23270000000; investmentsc: 1775000000 -> 3854000000 |
| ARQ | 2021-10-28 | 2021-10-01 | 2021-Q3 | cashneq: 13145000000 -> 11301000000; cashnequsd: 13145000000 -> 11301000000; ev: 270623310025 -> 272467310025; evebitda: 17.929 -> 18.051; invcap: 74779000000 -> 76623000000; investments: 20905000000 -> 22749000000; investmentsc: 1724000000 -> 3568000000 |
| ARQ | 2022-02-22 | 2021-12-31 | 2021-Q4 | cashneq: 10926000000 -> 9684000000; cashnequsd: 10926000000 -> 9684000000; ev: 301848277622 -> 303090277622; evebitda: 19.548 -> 19.629; invcap: 71626000000 -> 72868000000; investments: 20115000000 -> 21357000000; investmentsc: 1699000000 -> 2941000000 |
| ARQ | 2022-04-28 | 2022-04-01 | 2022-Q1 | cashneq: 8417000000 -> 7681000000; cashnequsd: 8417000000 -> 7681000000; ev: 320219551440 -> 320955551440; evebitda: 20.226 -> 20.273; invcap: 73821000000 -> 74557000000; investments: 20925000000 -> 21661000000; investmentsc: 1939000000 -> 2675000000 |
| ARQ | 2022-07-27 | 2022-07-01 | 2022-Q2 | cashneq: 9752000000 -> 8976000000; cashnequsd: 9752000000 -> 8976000000; ev: 304643884254 -> 305419884254; evebitda: 22.007 -> 22.063; invcap: 70899000000 -> 71675000000; investments: 20242000000 -> 21018000000; investmentsc: 1867000000 -> 2643000000 |
| ARQ | 2022-10-26 | 2022-09-30 | 2022-Q3 | cashneq: 11247000000 -> 10127000000; cashnequsd: 11247000000 -> 10127000000; ev: 285172842749 -> 286292842749; evebitda: 20.164 -> 20.243; invcap: 66426000000 -> 67546000000; investments: 20278000000 -> 21398000000; investmentsc: 1973000000 -> 3093000000 |
| ARQ | 2023-02-21 | 2022-12-31 | 2022-Q4 | cashneq: 10562000000 -> 9519000000; cashnequsd: 10562000000 -> 9519000000; ev: 287323168623 -> 288366168623; evebitda: 20.822 -> 20.898; invcap: 67995000000 -> 69038000000; investments: 19834000000 -> 20877000000; investmentsc: 1069000000 -> 2112000000 |
| ARQ | 2023-04-26 | 2023-03-31 | 2023-Q1 | cashneq: 13170000000 -> 12004000000; cashnequsd: 13170000000 -> 12004000000; ev: 304056943911 -> 305222943911; evebitda: 20.895 -> 20.975; invcap: 69702000000 -> 70868000000; investments: 20206000000 -> 21372000000; investmentsc: 1125000000 -> 2291000000 |
| ARQ | 2023-07-27 | 2023-06-30 | 2023-Q2 | cashneq: 14431000000 -> 12564000000; cashnequsd: 14431000000 -> 12564000000; ev: 297206090061 -> 299073090061; evebitda: 19.42 -> 19.542; invcap: 68049000000 -> 69916000000; investments: 20683000000 -> 22550000000; investmentsc: 1263000000 -> 3130000000 |
| ARQ | 2023-10-24 | 2023-09-29 | 2023-Q3 | cashneq: 14215000000 -> 11883000000; cashnequsd: 14215000000 -> 11883000000; ev: 266510744388 -> 268842744388; evebitda: 17.138 -> 17.288; invcap: 66240000000 -> 68572000000; investments: 20580000000 -> 22912000000; investmentsc: 1220000000 -> 3552000000 |
| ARQ | 2024-02-20 | 2023-12-31 | 2023-Q4 | cashneq: 12363000000 -> 9366000000; cashnequsd: 12363000000 -> 9366000000; ev: 291467089398 -> 294464089398; evebitda: 18.662 -> 18.854; invcap: 70610000000 -> 73607000000; investments: 21089000000 -> 24086000000; investmentsc: 1300000000 -> 4297000000 |
| ARQ | 2024-05-02 | 2024-03-29 | 2024-Q1 | cashneq: 15203000000 -> 10443000000; cashnequsd: 15203000000 -> 10443000000; ev: 294397149481 -> 299157149481; evebitda: 19.091 -> 19.399; invcap: 66149000000 -> 70909000000; investments: 21358000000 -> 26118000000; investmentsc: 1716000000 -> 6476000000 |
| ARQ | 2024-07-29 | 2024-06-28 | 2024-Q2 | cashneq: 17399000000 -> 13708000000; cashnequsd: 17399000000 -> 13708000000; ev: 314446488464 -> 318137488464; evebitda: 20.176 -> 20.413; invcap: 66052000000 -> 69743000000; investments: 20701000000 -> 24392000000; investmentsc: 1594000000 -> 5285000000 |
| ARQ | 2024-10-24 | 2024-09-27 | 2024-Q3 | cashneq: 16377000000 -> 13938000000; cashnequsd: 16377000000 -> 13938000000; ev: 319801747387 -> 322240747387; evebitda: 20.69 -> 20.848; invcap: 74839000000 -> 77278000000; investments: 20824000000 -> 23263000000; investmentsc: 1787000000 -> 4226000000 |
| ARQ | 2025-02-20 | 2024-12-31 | 2024-Q4 | cashneq: 12848000000 -> 10828000000; cashnequsd: 12848000000 -> 10828000000; ev: 332916067666 -> 334936067666; evebitda: 21.072 -> 21.2; invcap: 75534000000 -> 77554000000; investments: 19810000000 -> 21830000000; investmentsc: 1723000000 -> 3743000000 |
| ARQ | 2025-05-01 | 2025-03-28 | 2025-Q1 | cashneq: 11996000000 -> 8417000000; cashnequsd: 11996000000 -> 8417000000; ev: 343966175752 -> 347545175752; evebitda: 21.502 -> 21.726; invcap: 83265000000 -> 86844000000; investments: 20160000000 -> 23739000000; investmentsc: 1791000000 -> 5370000000 |
| ARQ | 2025-07-24 | 2025-06-27 | 2025-Q2 | cashneq: 12248000000 -> 9590000000; cashnequsd: 12248000000 -> 9590000000; ev: 334581407113 -> 337239407113; evebitda: 18.798 -> 18.947; invcap: 87309000000 -> 89967000000; investments: 21428000000 -> 24086000000; investmentsc: 2049000000 -> 4707000000 |
| ARQ | 2025-10-23 | 2025-09-26 | 2025-Q3 | cashneq: 13874000000 -> 12732000000; cashnequsd: 13874000000 -> 12732000000; ev: 334396522619 -> 335538522619; evebitda: 17.995 -> 18.056; invcap: 84911000000 -> 86053000000; investments: 22230000000 -> 23372000000; investmentsc: 1907000000 -> 3049000000 |
| ARQ | 2026-02-20 | 2025-12-31 | 2025-Q4 | cashneq: 13872000000 -> 10270000000; cashnequsd: 13872000000 -> 10270000000; ev: 374989729829 -> 378591729829; evebitda: 20.083 -> 20.276; invcap: 87133000000 -> 90735000000; investments: 22169000000 -> 25771000000; investmentsc: 1934000000 -> 5536000000 |
| ARQ | 2026-04-30 | 2026-04-03 | 2026-Q1 | cashneq: 11083000000 -> 10574000000; cashnequsd: 11083000000 -> 10574000000; ev: 371670515242 -> 372179515242; evebitda: 19.384 -> 19.411; invcap: 86772000000 -> 87281000000; investments: 23140000000 -> 23649000000; investmentsc: 2737000000 -> 3246000000 |
| ARQ | 2026-07-29 | 2026-07-03 | 2026-Q2 | cashneq: 13529000000 -> 12907000000; cashnequsd: 13529000000 -> 12907000000; ev: 413285086566 -> 413907086566; evebitda: 20.932 -> 20.964; invcap: 84780000000 -> 85402000000; investments: 23624000000 -> 24246000000; investmentsc: 2842000000 -> 3464000000 |
| MRQ | 2016-12-31 | 2016-12-31 | 2016-Q4 | cashneq: 18150000000 -> 8555000000; cashnequsd: 18150000000 -> 8555000000; ev: 203627297387 -> 214892297387; evebit: 23 -> 24; evebitda: 19.151 -> 20.21; invcap: 67169000000 -> 76764000000; investments: 21300000000 -> 30895000000; investmentsc: 4051000000 -> 13646000000 |
| MRQ | 2017-03-31 | 2017-03-31 | 2017-Q1 | cashneq: 21911000000 -> 12120000000; cashnequsd: 21911000000 -> 12120000000; ev: 209773514633 -> 219368514633; evebit: 25 -> 26; evebitda: 20.617 -> 21.56; invcap: 69316000000 -> 79107000000; investments: 21277000000 -> 31068000000; investmentsc: 3294000000 -> 13085000000 |
| MRQ | 2017-06-30 | 2017-06-30 | 2017-Q2 | cashneq: 22734000000 -> 11718000000; cashnequsd: 22734000000 -> 11718000000; ev: 217162283304 -> 226953283304; evebit: 31 -> 33; evebitda: 25.742 -> 26.903; invcap: 72028000000 -> 83044000000; investments: 26493000000 -> 37509000000; investmentsc: 4490000000 -> 15506000000 |
| MRQ | 2017-09-29 | 2017-09-29 | 2017-Q3 | cashneq: 22219000000 -> 12528000000; cashnequsd: 22219000000 -> 12528000000; ev: 218885341187 -> 229901341187; evebit: 30 -> 32; evebitda: 25.475 -> 26.758; invcap: 73199000000 -> 82890000000; investments: 27899000000 -> 37590000000; investmentsc: 5138000000 -> 14829000000 |
| MRQ | 2017-12-31 | 2017-12-31 | 2017-Q4 | cashneq: 15358000000 -> 6006000000; cashnequsd: 15358000000 -> 6006000000; ev: 222360416458 -> 232051416458; evebit: 29 -> 30; evebitda: 24.795 -> 25.875; invcap: 76393000000 -> 85745000000; investments: 27269000000 -> 36621000000; investmentsc: 5317000000 -> 14669000000 |
| MRQ | 2018-03-30 | 2018-03-30 | 2018-Q1 | cashneq: 15809000000 -> 8291000000; cashnequsd: 15809000000 -> 8291000000; ev: 217595320728 -> 226947320728; evebit: 27 -> 28; evebitda: 23.355 -> 24.358; invcap: 77920000000 -> 85438000000; investments: 28081000000 -> 35599000000; investmentsc: 5564000000 -> 13082000000 |
| MRQ | 2018-06-29 | 2018-06-29 | 2018-Q2 | cashneq: 13818000000 -> 7975000000; cashnequsd: 13818000000 -> 7975000000; ev: 219773817811 -> 227291817811; evebit: 26 -> 27; evebitda: 22.848 -> 23.629; invcap: 74316000000 -> 80159000000; investments: 27155000000 -> 32998000000; investmentsc: 5536000000 -> 11379000000 |
| MRQ | 2018-09-28 | 2018-09-28 | 2018-Q3 | cashneq: 13792000000 -> 9065000000; cashnequsd: 13792000000 -> 9065000000; ev: 229425487827 -> 235268487827; evebit: 25 -> 26; evebitda: 22.188 -> 22.753; invcap: 69637000000 -> 74364000000; investments: 27005000000 -> 31732000000; investmentsc: 5055000000 -> 9782000000 |
| MRQ | 2018-12-31 | 2018-12-31 | 2018-Q4 | cashneq: 11102000000 -> 9077000000; cashnequsd: 11102000000 -> 9077000000; ev: 232590933070 -> 237317933070; evebit: 25 -> 26; evebitda: 22.761 -> 23.223; invcap: 65959000000 -> 67984000000; investments: 25292000000 -> 27317000000; investmentsc: 5013000000 -> 7038000000 |
| MRQ | 2019-03-29 | 2019-03-29 | 2019-Q1 | cashneq: 7183000000 -> 5645000000; cashnequsd: 7183000000 -> 5645000000; ev: 232946433853 -> 234971433853; evebitda: 22.143 -> 22.336; invcap: 74744000000 -> 76282000000; investments: 24963000000 -> 26501000000; investmentsc: 4765000000 -> 6303000000 |
| MRQ | 2019-06-28 | 2019-06-28 | 2019-Q2 | cashneq: 9303000000 -> 6731000000; cashnequsd: 9303000000 -> 6731000000; ev: 254314581452 -> 255852581452; evebitda: 23.87 -> 24.015; invcap: 69471000000 -> 72043000000; investments: 24370000000 -> 26942000000; investmentsc: 4058000000 -> 6630000000 |
| MRQ | 2019-09-27 | 2019-09-27 | 2019-Q3 | cashneq: 9532000000 -> 7531000000; cashnequsd: 9532000000 -> 7531000000; ev: 268003050103 -> 270575050103; evebit: 26 -> 27; evebitda: 23.427 -> 23.652; invcap: 68947000000 -> 70948000000; investments: 23023000000 -> 25024000000; investmentsc: 3456000000 -> 5457000000 |
| MRQ | 2019-12-31 | 2019-12-31 | 2019-Q4 | cashneq: 7947000000 -> 6480000000; cashnequsd: 7947000000 -> 6480000000; ev: 270090597717 -> 272091597717; evebitda: 20.725 -> 20.879; invcap: 67458000000 -> 68925000000; investments: 23107000000 -> 24574000000; investmentsc: 3228000000 -> 4695000000 |
| MRQ | 2020-03-27 | 2020-03-27 | 2020-Q1 | cashneq: 15274000000 -> 13561000000; cashnequsd: 15274000000 -> 13561000000; ev: 218482718428 -> 219949718428; evebitda: 15.761 -> 15.867; invcap: 68897000000 -> 70610000000; investments: 21064000000 -> 22777000000; investmentsc: 2392000000 -> 4105000000 |
| MRQ | 2020-06-26 | 2020-06-26 | 2020-Q2 | cashneq: 17588000000 -> 10037000000; cashnequsd: 17588000000 -> 10037000000; ev: 222247416250 -> 223960416250; evebitda: 16.91 -> 17.04; invcap: 75139000000 -> 82690000000; investments: 21163000000 -> 28714000000; investmentsc: 2228000000 -> 9779000000 |
| MRQ | 2020-09-25 | 2020-09-25 | 2020-Q3 | cashneq: 18732000000 -> 11385000000; cashnequsd: 18732000000 -> 11385000000; ev: 244018784134 -> 251569784134; evebit: 22 -> 23; evebitda: 19.29 -> 19.887; invcap: 76508000000 -> 83855000000; investments: 21983000000 -> 29330000000; investmentsc: 2396000000 -> 9743000000 |
| MRQ | 2020-12-31 | 2020-12-31 | 2020-Q4 | cashneq: 8566000000 -> 6795000000; cashnequsd: 8566000000 -> 6795000000; ev: 269806314122 -> 277153314122; evebit: 24 -> 25; evebitda: 21.243 -> 21.821; invcap: 78372000000 -> 80143000000; investments: 22433000000 -> 24204000000; investmentsc: 2348000000 -> 4119000000 |
| MRQ | 2021-04-02 | 2021-04-02 | 2021-Q1 | cashneq: 10355000000 -> 8484000000; cashnequsd: 10355000000 -> 8484000000; ev: 260508956107 -> 262279956107; evebitda: 20.493 -> 20.632; invcap: 79345000000 -> 81216000000; investments: 22006000000 -> 23877000000; investmentsc: 2234000000 -> 4105000000 |
| MRQ | 2021-07-02 | 2021-07-02 | 2021-Q2 | cashneq: 11267000000 -> 9188000000; cashnequsd: 11267000000 -> 9188000000; ev: 268234858538 -> 270105858538; evebit: 20 -> 21; evebitda: 18.325 -> 18.452; invcap: 76730000000 -> 78809000000; investments: 21191000000 -> 23270000000; investmentsc: 1775000000 -> 3854000000 |
| MRQ | 2021-10-01 | 2021-10-01 | 2021-Q3 | cashneq: 13145000000 -> 11301000000; cashnequsd: 13145000000 -> 11301000000; ev: 259608123633 -> 261687123633; evebitda: 17.199 -> 17.337; invcap: 74779000000 -> 76623000000; investments: 20905000000 -> 22749000000; investmentsc: 1724000000 -> 3568000000 |
| MRQ | 2021-12-31 | 2021-12-31 | 2021-Q4 | cashneq: 10926000000 -> 9684000000; cashnequsd: 10926000000 -> 9684000000; ev: 284315872174 -> 286159872174; evebitda: 18.413 -> 18.532; invcap: 71626000000 -> 72868000000; investments: 20115000000 -> 21357000000; investmentsc: 1699000000 -> 2941000000 |
| MRQ | 2022-04-01 | 2022-04-01 | 2022-Q1 | cashneq: 8417000000 -> 7681000000; cashnequsd: 8417000000 -> 7681000000; ev: 304406206874 -> 305648206874; evebitda: 19.227 -> 19.306; invcap: 73821000000 -> 74557000000; investments: 20925000000 -> 21661000000; investmentsc: 1939000000 -> 2675000000 |
| MRQ | 2022-07-01 | 2022-07-01 | 2022-Q2 | cashneq: 9752000000 -> 8976000000; cashnequsd: 9752000000 -> 8976000000; ev: 312373149444 -> 313109149444; evebitda: 22.565 -> 22.619; invcap: 70899000000 -> 71675000000; investments: 20242000000 -> 21018000000; investmentsc: 1867000000 -> 2643000000 |
| MRQ | 2022-09-30 | 2022-09-30 | 2022-Q3 | cashneq: 11247000000 -> 10127000000; cashnequsd: 11247000000 -> 10127000000; ev: 274414726327 -> 275190726327; evebitda: 19.403 -> 19.458; invcap: 66426000000 -> 67546000000; investments: 20278000000 -> 21398000000; investmentsc: 1973000000 -> 3093000000 |
| MRQ | 2022-12-31 | 2022-12-31 | 2022-Q4 | cashneq: 10562000000 -> 9519000000; cashnequsd: 10562000000 -> 9519000000; ev: 303422288723 -> 304542288723; evebitda: 21.989 -> 22.07; invcap: 67995000000 -> 69038000000; investments: 19834000000 -> 20877000000; investmentsc: 1069000000 -> 2112000000 |
| MRQ | 2023-03-31 | 2023-03-31 | 2023-Q1 | cashneq: 13170000000 -> 12004000000; cashnequsd: 13170000000 -> 12004000000; ev: 296971691299 -> 298014691299; evebitda: 20.408 -> 20.479; invcap: 69702000000 -> 70868000000; investments: 20206000000 -> 21372000000; investmentsc: 1125000000 -> 2291000000 |
| MRQ | 2023-06-30 | 2023-06-30 | 2023-Q2 | cashneq: 14431000000 -> 12564000000; cashnequsd: 14431000000 -> 12564000000; ev: 289656098542 -> 290822098542; evebitda: 18.927 -> 19.003; invcap: 68049000000 -> 69916000000; investments: 20683000000 -> 22550000000; investmentsc: 1263000000 -> 3130000000 |
| MRQ | 2023-09-29 | 2023-09-29 | 2023-Q3 | cashneq: 14215000000 -> 11883000000; cashnequsd: 14215000000 -> 11883000000; ev: 269270822576 -> 271137822576; evebitda: 17.315 -> 17.435; invcap: 66240000000 -> 68572000000; investments: 20580000000 -> 22912000000; investmentsc: 1220000000 -> 3552000000 |
| MRQ | 2023-12-31 | 2023-12-31 | 2023-Q4 | cashneq: 12363000000 -> 9366000000; cashnequsd: 12363000000 -> 9366000000; ev: 280734775823 -> 283066775823; evebit: 19 -> 20; evebitda: 17.975 -> 18.124; invcap: 71126000000 -> 74123000000; investments: 20971000000 -> 23968000000; investmentsc: 1300000000 -> 4297000000 |
| MRQ | 2024-03-29 | 2024-03-29 | 2024-Q1 | cashneq: 15203000000 -> 10443000000; cashnequsd: 15203000000 -> 10443000000; ev: 293537068358 -> 296534068358; evebitda: 19.035 -> 19.229; invcap: 66149000000 -> 70909000000; investments: 21358000000 -> 26118000000; investmentsc: 1716000000 -> 6476000000 |
| MRQ | 2024-06-28 | 2024-06-28 | 2024-Q2 | cashneq: 17399000000 -> 13708000000; cashnequsd: 17399000000 -> 13708000000; ev: 301548355291 -> 306308355291; evebitda: 19.349 -> 19.654; invcap: 66052000000 -> 69743000000; investments: 20701000000 -> 24392000000; investmentsc: 1594000000 -> 5285000000 |
| MRQ | 2024-09-27 | 2024-09-27 | 2024-Q3 | cashneq: 16377000000 -> 13938000000; cashnequsd: 16377000000 -> 13938000000; ev: 335823434488 -> 339514434488; evebit: 23 -> 24; evebitda: 21.726 -> 21.965; invcap: 74839000000 -> 77278000000; investments: 20824000000 -> 23263000000; investmentsc: 1787000000 -> 4226000000 |
| MRQ | 2024-12-31 | 2024-12-31 | 2024-Q4 | cashneq: 12848000000 -> 10828000000; cashnequsd: 12848000000 -> 10828000000; ev: 298090449812 -> 300529449812; evebitda: 18.868 -> 19.022; invcap: 75534000000 -> 77554000000; investments: 19810000000 -> 21830000000; investmentsc: 1723000000 -> 3743000000 |
| MRQ | 2025-03-28 | 2025-03-28 | 2025-Q1 | cashneq: 11996000000 -> 8417000000; cashnequsd: 11996000000 -> 8417000000; ev: 334335397796 -> 336355397796; evebit: 22 -> 23; evebitda: 20.9 -> 21.026; invcap: 83265000000 -> 86844000000; investments: 20160000000 -> 23739000000; investmentsc: 1791000000 -> 5370000000 |
| MRQ | 2025-06-27 | 2025-06-27 | 2025-Q2 | cashneq: 12248000000 -> 9590000000; cashnequsd: 12248000000 -> 9590000000; ev: 339834079684 -> 343413079684; evebit: 20 -> 21; evebitda: 19.093 -> 19.294; invcap: 87309000000 -> 89967000000; investments: 21428000000 -> 24086000000; investmentsc: 2049000000 -> 4707000000 |
| MRQ | 2025-09-26 | 2025-09-26 | 2025-Q3 | cashneq: 13874000000 -> 12732000000; cashnequsd: 13874000000 -> 12732000000; ev: 319819828439 -> 322477828439; evebitda: 17.21 -> 17.353; invcap: 84911000000 -> 86053000000; investments: 22230000000 -> 23372000000; investmentsc: 1907000000 -> 3049000000 |
| MRQ | 2025-12-31 | 2025-12-31 | 2025-Q4 | cashneq: 13872000000 -> 10270000000; cashnequsd: 13872000000 -> 10270000000; ev: 334267474354 -> 335409474354; evebitda: 17.902 -> 17.963; invcap: 87133000000 -> 90735000000; investments: 22169000000 -> 25771000000; investmentsc: 1934000000 -> 5536000000 |
| MRQ | 2026-04-03 | 2026-04-03 | 2026-Q1 | cashneq: 11083000000 -> 10574000000; cashnequsd: 11083000000 -> 10574000000; ev: 361571473854 -> 365173473854; evebitda: 18.857 -> 19.045; invcap: 86772000000 -> 87281000000; investments: 23140000000 -> 23649000000; investmentsc: 2737000000 -> 3246000000 |
| MRQ | 2026-07-03 | 2026-07-03 | 2026-Q2 | cashneq: 13529000000 -> 12907000000; cashnequsd: 13529000000 -> 12907000000; ev: 394817870651 -> 395326870651; evebitda: 19.997 -> 20.023; invcap: 84780000000 -> 85402000000; investments: 23624000000 -> 24246000000; investmentsc: 2842000000 -> 3464000000 |
