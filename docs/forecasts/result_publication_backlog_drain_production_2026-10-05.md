# Result-publication backlog drain: production

Date: 2026-10-05 (Europe/Helsinki)

## Authorization and implementation

The user's prod-drain-apply task explicitly authorized exactly one supervised
production maintenance apply, including verified rollback backups, journal
updates and new immutable-generation activation. Environment escalation accepted
this authorization. Implementation commit 42ddb6eee612909369fd55ada4ea07ecdfd1efa5
is contained in HEAD; the four relevant source modules are unchanged from it.
No source changes or resolver changes were needed.

The validated architecture remains candidate-only publication enrichment followed
by final verification and journaled immutable-generation activation. The source
hierarchy, matching, pacing and company transaction semantics were not changed.
Yahoo was not used as canonical authority. No open case was forced VERIFIED.

## Fresh discovery and scope drift

Source generation:
refresh_20261004T173815Z_refresh_fundamentals_1c0cfaa31765_production_0452fc80.

Fresh read-only discovery at as-of 2026-10-05 selected all 283 eligible quarters:

| Status | Before | After |
| --- | ---: | ---: |
| MISSING | 0 | 0 |
| UNRESOLVED | 58 | 53 |
| NOT_FOUND | 199 | 199 |
| AMBIGUOUS | 26 | 26 |
| Total recent open | 283 | 278 |

VERIFIED was explicitly checked to have no intersection with selected keys.
Selection priority remains MISSING, UNRESOLVED, NOT_FOUND, AMBIGUOUS, with
newest context then stable natural identity ordering. First three keys:
(707,2027,Q1), (394,2027,Q1), (1225,2027,Q2). Last three:
(1712,2026,Q2), (1878,2026,Q2), (2026,2026,Q2).

Yesterday's 332-key selection was reproduced read-only against the same active
generation at as-of 2026-10-04. Advancing the 60-day horizon removed exactly 49
keys and added none: 14 UNRESOLVED, 26 NOT_FOUND and 9 AMBIGUOUS aged out.
This is deterministic date-boundary drift, not a generation change or resolution.
The production apply used today's scope, without extending the horizon.

## Preflight and command

Before the CLI was invoked, active role hashes matched the generation manifest;
all three role databases passed quick_check=ok and foreign_key_check=0. Existing
journal guard passed, available disk exceeded three times source role sizes,
and the existing backup parent was present. Source, forecasts, scheduler config
and review-queue hashes were recorded. The implementation then acquired its
existing production/scheduler lock, guarded the journal and reselected scope.

Exactly one production command was invoked:

```bash
python3 -m rawcandle.cli.result_publication_backlog_drain \
  --retry-days 60 \
  --network-budget-seconds 1800 \
  --apply \
  --confirm-production
```

Runtime result artifact:
fundamental_reports/publication_drains/publication_drain_20261005T064921Z_43a1e040/result.json.
Independent supervisor safety/overlap artifact:
/tmp/publication_drain_production_2026-10-05.json.

## Production outcome and performance

- Workflow status PARTIAL, CLI exit 2, errors empty.
- Selected/attempted/processed: 283; unprocessed: 0.
- New VERIFIED: 5; still-open retry-eligible: 278.
- SEC metadata requests: 281; document requests: 153; total: 434.
- Cache hits: 1; retries: 0; transient failures: 0; HTTP failures: 0; 429: 0.
  Zero counters are absent from the sparse SEC stats dictionary.
- Candidate publication elapsed: 125.598 seconds.
- Complete drain elapsed including generation work: 145.828 seconds.
- Finite network budget: 1800 seconds; not exhausted. Network-only elapsed is
  not separately instrumented; candidate publication elapsed includes DB work.
- Activated generation: publication_drain_20261005T064921Z_43a1e040.
- Journal COMPLETED; manifest/hash/postflight PASS; rollback NOT_REQUIRED.

New VERIFIED identities (all outside the forecast-history window):

| Ticker | Fiscal identity | Publication timestamp UTC |
| --- | --- | --- |
| ACVA | 2026 Q2 | 2026-08-10T20:11:55Z |
| BYND | 2026 Q2 | 2026-08-05T21:13:27Z |
| CNNE | 2026 Q2 | 2026-08-10T20:11:10Z |
| ITW | 2026 Q2 | 2026-07-28T13:21:11Z |
| SLAB | 2026 Q2 | 2026-08-11T20:14:32Z |

## Retained backups and hashes

Backup directory (all retained, no cleanup):
backups/fundamentals_admin_production/publication_drain_20261005T064921Z_43a1e040/.

Each immutable-generation copy equals its source hash, quick_check is ok and
foreign_key_errors is zero:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| provider.db | 968331264 | 2b3a57add8b51413d98f220d4cdd313994d1a4079f987a94796bf6a2b6db5fbb |
| canonical.db | 674914304 | f727d5f19ceb388cc4d01110cab54712817d4e79b5ab84c6214f4bbe0402e3b2 |
| analysis.db | 910483456 | a8dcc37e1a0e2442dd44023b63d8c6ba91ee5fdce3ab05e2fa5407413a0355ce |

New canonical size: 674926592 bytes; finalized SHA-256:
6fb73fe67e9d28407012ebb76e9b57951e409898b817a4eca94e58d934d4b5c2.
Provider/analysis hashes remain identical to source. Active manifest role hashes
were independently compared with postflight verification and all matched.
No manual database replacement or recovery was necessary.

## Financial, identity and forecast safety

Symmetric EXCEPT comparisons between old and new v4_quarter,
v4_quarter_financials, company and security returned no differences. Provider
history and analysis outputs are byte-identical. All old immutable role hashes
remain unchanged. No duplicate publication evidence hashes were found.

Forecasts DB pre/post SHA-256 was identical:
5cc1b771ecfab2e1e31e5d2d55f6947b8c26a54b7d381e8d90f230df16f32aec.
Scheduler configuration pre/post SHA-256 was identical:
3a0b74412a0fb9cf5e7a9b370e97a6d48af031d5094d53b5689669e630c9e894.
Review queue also remained byte-identical. No forecast timer/service change
command was issued; no scheduler source changes were made.

Narrow read-only count of VERIFIED publication timestamps inside the actual
FISCAL_ESTIMATE fetched-time window: before 7, after 7. Newly overlapping tickers:
none. No forecast revision engine changes or broad study were performed.

## Regression, tests and follow-up

Normal refresh default is still 100 RECENT_OPEN_RETRY quarters and all uncapped
NEW_THIS_REFRESH, using 60 days and the unchanged 300-second normal budget.
Read-only selection after activation selected 100 and left 178 unattempted.
Unlimited selection remains explicitly manual/operator-only.

Focused smoke tests: python3 -m pytest -q tests/test_publication_backlog_drain.py;
13 passed in 10.46 seconds. No broad financial/valuation/DC suites were run.

The follow-up investigation backlog is 278 CURRENT recent-open rows:
53 UNRESOLVED, 199 NOT_FOUND, 26 AMBIGUOUS. This is not the entire historical
open population. Global authority counts are 860 UNRESOLVED, 1916 NOT_FOUND,
651 AMBIGUOUS and 12803 VERIFIED; 49 aged-out selected keys also remain open.
Neither attempting every row nor shrinking the horizon population clears them.

Next: investigate persistent open cases separately by root cause and evidence
availability, using targeted official evidence rather than repeatedly draining
or weakening matching/authority rules. Preserve backups and completed journal.

RESULT_PUBLICATION_BACKLOG_DRAIN_PRODUCTION_COMPLETE
