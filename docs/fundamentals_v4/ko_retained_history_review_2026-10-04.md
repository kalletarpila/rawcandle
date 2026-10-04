# KO retained-history evidence review

Date: 2026-10-04

Decision: `KO_ACCEPT_RETAINED_HISTORY_NOT_SAFE`

Meaning: approval is not sufficiently proven from this exact persisted evidence;
this is NOT a finding that KO's retained historical financial data is incorrect.
No approval, new Preview, Test or Production was executed.

## Exact evidence identity

Preview: `20261004T132346Z_refresh_fundamentals_bee6f4d28686`.
Refresh-set fingerprint:
`5f3a4cc56c4756c05613674a0d30b5fe3af818b2c470395f54fa73390443ee78`.
Partition fingerprint:
`6cb90c7c113856547b91d617f0118458a4dc5cd3e00de14c4016e57c84cd33c7`.
Queue item:
`666db8590ea8f6cc8599ba837fc833d974d148b50ec952d5b2d3cd408c4f3311`.
Source-evidence fingerprint:
`7824ff66d6c33f40917c9159a62d76dbb22f03e8b2432452dc8811c68480ba0d`.
Queue evidence fingerprint:
`4b7a1b37d197f00c44add9f0394b128cefaa51d8eaeff77c7db980ded1c02f5a`.
Retained-plan fingerprint:
`22d07664683d7be13271f8261eacaf8d184b32c2b8a98169e0461387df7041b3`.

KO is OPEN / PROVIDER_ANOMALY_SUSPECTED, company 1231, security 1235,
CIK 0000021344, provider security 199839. Its exact source events, stored
locality proof and queue row were inspected read-only. First observed hold was
20261004T022125Z; latest stored review points to the specified Preview.
The queue's reasons are the structured boundary/prefix reasons, while the
comparison's review_reason is AMBIGUOUS_SOURCE_REMOVAL.

## Three distinct missing observations

All are SHARADAR/fundamentals observations. Source key is
(ticker, dimension, date, reportperiod). All three have stored original SUCCESS
payloads fetched at 2026-09-10T13:37:58Z, source lastupdated 2026-07-29, and remain
in the currently accepted provider generation. The fetched timestamp is direct
observed-presence evidence; source lastupdated is not a fetch timestamp.

| Key | Fiscal identity / period end | Exact Preview accessible presence | Retained provider / canonical | Boundary |
|---|---|---|---|---|
| KO, ARQ, 2016-07-28, 2016-07-01 | 2016-Q2 / 2016-07-01 | Absent | Present / quarter 43777 present | Span 41, AGED_OUT |
| KO, MRQ, 2016-07-01, 2016-07-01 | 2016-Q2 / 2016-07-01 | Absent | Present / same Q2 canonical via ARQ | Span 41, AGED_OUT |
| KO, MRQ, 2016-09-30, 2016-09-30 | 2016-Q3 / 2016-09-30 | Absent | Present / quarter 43778 present via ARQ | Span 40, AMBIGUOUS |

Presence here is as of the exact persisted Preview, not an independently fetched
new live Sharadar response. No new provider request was made in this task.

Original provider content hashes in table order:

- `940a7966081c3e8e10726ed8b84e39b723f58826392bf3ec2e31d2cfeb3f73fd`
- `24403fe9aa09a17771ab6d880cc7a7a97305bb497f71fb43ed1cd7f1e96ec678`
- `0edd17bf73bfec0b052bd5080dbd23006fb5947a58d2961264a08b0b66d007d1`

Recomputed effective fingerprints of original payloads match retained-row fingerprints:

- ARQ Q2: `ffe39392e3a36b12713dc4be8da72027d2fce62cc8236d007cc71a1d85167419`
- MRQ Q2: `bbf5bb763824c40c69bf5164d4747f3f386e628d5fe37f4d2ed031a569867ffe`
- MRQ Q3: `a354da7330af6d11e1a2b6004574f2a64eebc49e378358280cd1fa3b488fa970`

## Fiscal window and the two normal aging rows

The persisted COMPLETE ARQ response has 40 rows, oldest reportperiod 2016-09-30
(2016-Q3), latest 2026-07-03 (2026-Q2). COMPLETE MRQ has 39 rows, oldest
2016-12-31 (2016-Q4), same latest quarter. Accepted provider history still has
41 observations in each dimension.

2016-Q2 to 2026-Q2 spans 40 quarter steps plus the inclusive boundary = 41.
2016-Q3 to 2026-Q2 spans 39 steps plus the inclusive boundary = 40.
The existing minimum boundary span is 41; it is not reduced here.

OLDEST_PREFIX_EXPECTED_FISCAL_WINDOW applies to the two Q2 rows: complete source,
coherent chronology, clean oldest prefix, absent keys, no same-fiscal current
replacement, and expected fiscal boundary covered. Stored locality proof rules
out companion/cross-ticker replacement conflicts. These two meet the existing
RETAINED_OUTSIDE_SOURCE_WINDOW aging contract and must not be deleted or rewritten.

The MRQ Q3 row is also in a clean oldest prefix, but its span is 40 and MRQ returns
one fewer quarter than ARQ. Therefore BOUNDARY_FISCAL_WINDOW_TOO_SHORT applies.
Uneven provider truncation is a plausible non-removal explanation, not a proven
provider policy. True upstream MRQ removal cannot be independently excluded.

## Third-row alternatives and the blocking limitation

All three source events have same_fiscal_current_keys=[], no source reappearance,
and no fiscal-revision event. Retained ARQ Q3 exists at date 2016-10-27 and matches
the canonical quarter. That ARQ counterpart supports a real historical Q3 but is
NOT an interchangeable MRQ replacement. Stored evidence identifies no revised
MRQ date or alternative fiscal label.

An independent subtraction check removed the exact three missing keys from the
accepted histories, then used the current history_fingerprints implementation.
Resulting row counts equal Preview counts, but BOTH effective fingerprints differ:

| Dimension | Retained history minus missing keys | Exact Preview accessible history |
|---|---|---|
| ARQ | 55d3f3faa68762415a3258a42194f77b2f4fee47854319a1d287420a92e5398c | 6db386cf456425d918ee5f0b9172ac91587a37cbc36a2a748bf0f340e41df69c |
| MRQ | cd11ab196a4b0f93734476529841b02b63bf4aff01e05197fe3deb55d05604c2 | d1a32c0f113d7070479884cb0dc822230361ffcca5f28f76a508698e3b3a4bf6 |

Raw fingerprints differ too. This does not identify a specific revision or deletion;
it proves that the accessible response cannot be independently reconstructed as
unchanged accepted rows minus only these keys. Preview artifacts retain hashes and
removal evidence, not the complete incoming KO raw rows needed to locate the
differences. A held comparison exits on removal ambiguity before normal effective
change classification; zero published/candidate impact does not prove zero incoming
payload changes. No new incoming financial values have been applied.

## Provider/canonical parity

Independently compared all 18 directly mapped financial fields for ARQ Q2 and Q3
against canonical rows: PASS, including period/fiscal identity. Q2 revenue/net income
are 11,539,000,000 / 3,448,000,000; Q3 are 10,633,000,000 / 1,046,000,000.
Original missing-row payload fingerprints also match their retained provider state.
MRQ sharesbas differs from ARQ, as stored in the original observations; canonical
policy is SHARADAR_ARQ_PRIMARY, so MRQ is not silently substituted into canonical.

This proves accepted-state internal consistency, not absent incoming changes.
There was no candidate build in the exact run; added/changed/removed canonical
impact is zero because the ticker remains quarantined. Persisted events contain
no fiscal reclassification, but complete incoming-row parity remains unverified.

## Official supporting evidence

The [official KO Q3 2016 release](https://investors.coca-colacompany.com/news-events/press-releases/detail/860/the-coca-cola-company-reports-third-quarter-2016-results)
reports the quarter ended September 30, 2016, revenue $10,633 million, gross profit
$6,502 million and operating income $2,271 million. These match retained values.
It establishes the historical quarter's reality, not why Sharadar currently omits
one MRQ record. The October 26 release date is not used to rewrite provider date
2016-10-27 or any canonical publication authority. SwingMaster V3 was not used:
older secondary data cannot establish the reason for this current Sharadar omission.

## Operator contract and decision

retained_history_approval_eligibility returns eligible=true for the exact stored
item, with affected_source_count=3. Eligibility is necessary operational capability,
not evidence that every substantive SAFE criterion in this task has been met.

ACCEPT_RETAINED_HISTORY writes evidence-bound approval/audit only, not financial DBs.
It preserves historical source status rather than claiming currently returned rows.
Natural identity, source keys, fiscal identities, evidence fingerprint, queue item,
published-generation binding and locality context are bound. Later material drift
invalidates approval; no whitelist or global boundary bypass is introduced.

Important status correction: the existing action initially sets RETRY_REEVALUATION,
NOT immediately RESOLVED. The existing normal Preview/production consumption
lifecycle controls final resolution. The task's immediate RESOLVED expectation
must not be implemented with direct SQL.

Decision: NOT_SAFE for execution now. The missing Q3 MRQ row is real and retained
consistently, but provider truncation versus deliberate upstream removal is not
proven and incoming payload differences are unlocated. Approval was NOT executed.
KO remains OPEN with operator_action NULL.

## Safety and next action

Read-only financial DBs; current repeated pre/post hashes matched:

- Provider: `5192c9c7d2020b9897a39ab06c864fb9e35e3696e956de26f7ee52de37cd3270`
- Canonical: `765a5efdc601dc99c6969ef0e3fe80c2206472b91437486cf5b6b73fa8370a89`
- Analysis: `6c1487278f25eb118ecfb4312966ba65b8a241ff0d20694d698f097e06c95b23`
- Forecasts: `5cc1b771ecfab2e1e31e5d2d55f6947b8c26a54b7d381e8d90f230df16f32aec`
- Queue: `d7322ec86b5fe6a8ce9ccfc6f3f90127738f6fe82007e056e0f6c02cc052b914`

The forecast hash is current, not compared with an old task's hash. Financial,
publication and queue write count: zero. Scheduler/systemd changes: zero.
No source changes, no pytest runs or broad suite; targeted read-only assertions
verified provenance, parity, fingerprint comparison and action eligibility.

Next step: retain KO OPEN. Obtain a KO-only complete ARQ/MRQ raw provider response
or recovered exact Preview source artifact, locate the fingerprint differences,
and establish the MRQ boundary/removal explanation before approval. A newly fetched
response is a new evidence boundary, not retroactive proof of this Preview: if it
differs, run a fresh normal Preview and review its newly bound item. Do not run Test
or Production automatically, and do not approve solely because the UI action is enabled.
