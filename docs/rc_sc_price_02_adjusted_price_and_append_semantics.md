# RC-SC-PRICE-02: adjusted prices and append semantics

This report supersedes PRICE-01's broad historical-equality requirement. It does
not change RC's mathematical definitions or authorize a history rewrite. Related:
[measurements](rc_sc_price_02_mismatch_root_causes.md),
[split safety](rc_sc_price_02_split_safety_and_scheduler.md),
[plan](rc_sc_price_02_implementation_plan.md),
[acceptance](rc_sc_price_02_acceptance_evidence.md).

## Verified effective price definitions

RC's installed scheduler uses `/usr/bin/python3`, yfinance 0.2.66/pandas 2.3.3.
`main._build_stock_update_service_adapters` constructs yf.Ticker; the service calls
`stock.history(start,end)` with implicit auto_adjust=True, back_adjust=False,
actions=True, repair=False, keepna=False, rounding=False. StockCore's environment
uses yfinance 1.7.0/pandas 2.3.3 and explicitly requests auto_adjust=False,
back_adjust=False, actions=True, repair=False, keepna=True, rounding=False.

In **both installed versions**, the accepted six-field same-vintage reconstruction is:

```text
f = Adj Close / Close
adjusted Open, High, Low = ordinary field * f
adjusted Close = Adj Close directly
Volume = supplied volume, not multiplied by f or a split ratio
```

Running this calculation against each library's own utils.auto_adjust produced
bitwise-equal OHLC and unchanged volume for all **63,962 rows in 30 retained frames**
in each environment. Thus version differences do not change this formula. They
can still affect request construction, upstream responses, repairs/cleanup or metadata;
this experiment does not claim all library versions return identical observations.
No live Yahoo call was made. The earlier 11 independently retained True windows
(183 common rows) remain evidence that independent captures need not match bitwise.

StockCore ordinary OHLC is generally already split-adjusted. It is neither original
unsplit exchange prices nor dividend-adjusted OHLC. Ordinary Source prices cannot
be sent directly to an RC path expecting adjusted prices. Approved Source fallback
Adj Close→Close is an accepted observation with recorded provenance uncertainty,
not permission to infer a missing factor or recompute it from dividend cash amounts.

Canonical PriceReader Ordinary qualification, accepted quality.adjusted_usable,
finite positive same-vintage factor, required volume and action/route/dependency
checks must precede RC-local reconstruction. StockCore's adjusted reader remains
research-only; the bridge need not call it with research=True or change that policy.
Its Decimal reconstruction may differ in operation-order bits, so use the exact
RC-facing float/direct-Close operation on the same accepted snapshot's fields.

## RC already appends different vintages

`services/stock_update_service.py:resolve_effective_update_start_date` starts at
MAX(pvm)+one calendar day; start_override can only move later. There is **no daily
overlap request**. `insert_missing_ohlcv_rows` ignores existing ticker/date rows
without comparing or replacing their values. Its UNIQUE(osake,pvm) index and
in-memory date set suppress duplicates. Consequently:

- Historical dividend-adjustment changes and revised volumes already remain in
  stored history when direct Yahoo supplies a newer observation.
- Current code does not depend on exact historical equality between captures.
- A temporary Source adapter that reproduces the same adjusted definition can
  append new sessions without repairing old rows, provided current identity,
  quote/share units, actions and the append boundary are qualified.

The retained October 30/31 USA run logs corroborate real append activity. They do
not provide every row's original acquisition timestamp or currency. Those missing
facts must not be invented from numerical equality.

## Bounded boundary check

Use the RC latest stored session **b**, plus up to two preceding common observations
as diagnostic context, and the prospective new Source scope. Revalidate dated
identity, eligibility/calendar, quote/count units and current Source head/quality.
The actual anchor must be available and a valid finite positive ordered OHLC bar;
the adapter must never substitute an earlier good date to hide a missing/bad anchor.
Check each newly returned Source bar independently for accepted availability,
positive finite ordered OHLC, factor and volume. Return only dates strictly after b
inside the caller's half-open range.

Apply the recommended 0.1% OHLC and 1%/bounded-absolute volume comparison to Source
and RC on **the same anchor date**, rather than comparing prices on two different
sessions. A real overnight market move is not a unit error by magnitude alone.
Check context for unexplained persistent multipliers/steps and action boundaries;
use explicit split/identity/currency evidence regardless of numerical closeness.
Older bar revisions need not independently satisfy the new-session anchor tolerance.

For a qualified ordinary boundary, gross-return consistency is bounded algebraically:

```text
bridge gross return = new Source Close / stored RC anchor Close
Source gross return = new Source Close / reconstructed Source anchor Close
their ratio         = reconstructed Source anchor Close / stored RC anchor Close
```

The anchor gate therefore bounds additional cross-vintage return distortion without
limiting genuine daily returns. It does not certify an economic total-return series
or repair RC's preexisting history. Historical missing/invalid RC bars are reported,
not returned or accepted via tolerance. An invalid current anchor/new Source row
is an independent hold; an older legacy defect alone does not permanently block
otherwise compatible new-session appends.

## Newly recorded dividends: explain the change rather than widen tolerance

A strict adjusted-anchor comparison alone would permanently strand many dividend
payers after an ex-date: Source revises the old anchor's Adj Close, while RC's
insert-only writer retains its earlier vintage. Direct RC Yahoo already creates
that historical mixture. It is not a newly introduced Source-provider behavior.

A small, explicit compatibility path can preserve that existing contract **only when**:

1. All independent identity, currency, session, split and Source-quality gates pass.
2. Accepted RECORDED dividend evidence has an ex-date after b and within the first
   prospective new interval; no relevant held/unresolved dividend is used as evidence.
3. Source's **ordinary** OHLC on b matches stored RC OHLC within the price bound,
   so the apparent discrepancy is specifically the accepted current dividend factor.
4. The same-vintage accepted Adj Close/Close factor is finite, positive and below
   one for this positive-cash-dividend explanation. New bars use their own accepted
   factor and the normal RC formula; no factor is invented from cash sums.

This is an evidenced interpretation of the same legacy adjustment contract, not
permission to tolerate a 60% price error, change a split ratio, rescale volume,
change currency or switch new observations to ordinary OHLC. Log the named reason
LEGACY_DIVIDEND_VINTAGE_CONFIRMED and source/action receipts so the historical mixture
is explicit. A factor discrepancy with no such explanation remains a ticker-local hold.

**Concrete ARI example:** on October 29 RC/Source ordinary Close is 6.4499998093;
Source adjusted Close is 2.3499999046 after its recorded October 30 distribution.
October 30 Source adjusted Close and RC's independently stored new Close both equal
2.3299999237. The 63.6% historical adjustment is not admitted by increasing the
0.1% tolerance. The accepted ordinary-anchor/action evidence explains why exactly
the same new-row behavior occurs in the old Yahoo path. An isolated actual RC-writer
test appends the accepted new bar and proves that the old RC bar remains untouched.
If preserving this preexisting dividend-history mixture is unacceptable for an
individual consumer, withhold that ticker; a total-return-consistent history rewrite
is a different task and is not part of this bridge.

## Historical versus new-session evidence

| Class | Meaning and treatment |
| --- | --- |
| A: historical revision | Earlier adjusted factors/volumes differ, current anchor units agree; append may proceed with evidence and no old-row update |
| B: current unit/action/boundary conflict | Wrong/missing identity/currency, new/revised split, unexplained factor or material current anchor mismatch; skip ticker before RC insertion |
| C: insufficient evidence | Missing Source anchor, unqualified session, unresolved currency or unexplainable scale pattern; skip, not Yahoo fallback |
| New observation itself | Require current accepted Source quality/actions and the normal adjusted definition; do not compare to an unavailable fresh Yahoo oracle or assume tolerance proves Source acceptance |

At the actual study cutoff no uniquely mapped ticker has a newer qualified Source
session than RC. All 4,081 candidate counts are prospective, not live import counts.

A bounded historical holdout treats October 29 as the last RC date and October 30
as newly available Source data for the 931: 684 have a compatible/evidenced anchor
and a new bar within the numerical bounds of RC's retained October 30 observation;
50 anchor cases have a specifically explained new-dividend vintage. Other outcomes:
38 independent current hard holds, ten invalid October 29 legacy anchors, 12
unexplained price-anchor holds, 177 volume-anchor holds, eight new-observation
price disagreements and two new-volume disagreements against the retained RC oracle.
These sum to 931. The holdout uses today's accepted Source vintage, not a claim
about what StockCore knew historically at the time. It is comparison evidence;
runtime will use accepted Source authority without making a fresh Yahoo request.

## No-new-data and downstream behavior

If Source has no qualified date after RC b, return an empty, correctly shaped
DataFrame; do not send overlap to the writer. Existing `no_history_data` skips
per-ticker split/divergence/candlestick work. Already-current planning skips even
factory construction. No global run/freshness gate is needed. Qualified older
accepted prefixes can be used during incomplete Source acquisition; never fabricate
or jump across an unqualified Source session to reach a later bar.

If a nonempty duplicate frame is supplied, existing RC still calls split/backfill
and divergence even with zero inserted rows; candlesticks require positive inserts.
The bridge must not create that case by returning historical overlap. Final market
Dow and existing configured scheduler poststeps retain their current triggers even
when all ticker histories are empty. The study executes none of those production jobs.
