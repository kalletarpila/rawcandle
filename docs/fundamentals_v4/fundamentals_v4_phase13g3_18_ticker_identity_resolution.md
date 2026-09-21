# Phase 13G.3.18: Ticker Transition and Identity Resolution V1

## Scope and safety

This phase adds a generic identity resolver, a declarative review contract, a read-only Administration Preview, and Add Tickers candidate integration. It did not execute Add Tickers Test or Production and did not mutate provider, canonical, analysis, market, or taxonomy databases. Scheduler state was not changed.

## Architecture audit

RawCandle already separates the durable identity layers needed by V1:

| Structure | Role |
| --- | --- |
| `company` | Stable RawCandle company identity. One company may own multiple securities. |
| `security` | Stable security identity and current ticker. `current_ticker` is unique only for current securities. |
| `ticker_alias` | Provider-scoped ticker history with `valid_from` and `valid_to`. The same ticker text can occur on different securities over time. |
| `provider_security_identity` | Provider permanent identifier to one canonical security. |
| `provider_company_identity` | Provider company identifier to one canonical company. |
| `company_cik` | SEC CIK at company level. It does not prove security continuity. |

The schema supports multiple aliases for one security and multiple securities for one company. It has no explicit predecessor/successor edge. V1 does not add one: reviewed predecessor context is retained in the declarative registry, while canonical mutation uses the existing company, security, alias, and provider identity structures.

Ticker text is never used alone as a persistent join key. An exact current-ticker match is checked against stronger provider and CIK evidence before it is accepted. A historical alias does not authorize a join when current provider identity differs, which preserves ticker reuse.

### Permaticker contract

Sharadar describes its TICKERS table as its securities master and `permaticker` as the permanent ticker symbol. RawCandle's existing schema binds `(provider, provider_security_id)` uniquely to `security_id`. V1 therefore accepts the same exact Sharadar permaticker as security-continuity evidence only when it resolves to exactly one existing `provider_security_identity` row. Multiple mappings, or disagreement with company CIK evidence, fail closed.

Sources:

- Sharadar fundamentals and TICKERS metadata: https://sharadar.com/fundamentals
- Sharadar prices and securities-master metadata: https://sharadar.com/prices

## Resolver contract

The resolver models four independent dimensions:

- company continuity;
- security continuity;
- ticker relationship;
- provider identity continuity.

Its result classes are:

- `EXISTING_SECURITY`
- `NEW_SECURITY`
- `TICKER_TRANSITION_SAME_SECURITY`
- `BUSINESS_COMBINATION_NEW_SECURITY`
- `REORGANIZATION_SUCCESSOR`
- `IDENTITY_REVIEW_REQUIRED`

Classification and authority are separate. Authority is one of `LOCAL_DETERMINISTIC`, `APPROVED_REVIEW`, `PROPOSED_REVIEW`, or `INSUFFICIENT`. Only a deterministic result or an internally consistent `APPROVED` record can set `automatic_mutation_permitted=true`.

The decision chain is:

1. Exact Sharadar metadata for the requested ticker.
2. Exact canonical current ticker, checked against stronger evidence.
3. Unique canonical Sharadar permaticker mapping.
4. Company-level CIK mapping.
5. Historical alias evidence and ticker-reuse detection.
6. Declarative reviewed resolution when local evidence is insufficient.

Provider ambiguity, multiple canonical identities, permaticker/CIK disagreement, stale reviewed references, and provider/review disagreement all produce `IDENTITY_REVIEW_REQUIRED`.

## Reviewed resolution registry

The version-controlled registry is `rawcandle/fundamentals/admin/identity_resolutions.json`. Each record includes the subject ticker, effective date, resolution class, all continuity dimensions, predecessor and canonical references where applicable, CIK/permaticker/exchange evidence, source records, review status, and reason.

Status semantics:

- `PROPOSED`: research evidence only; never authorizes mutation.
- `APPROVED`: may authorize mutation if current local state still agrees with the record.
- `REJECTED`: retained audit evidence; never authorizes mutation.

Runtime does not browse the web. External facts enter the mutation-capable system only through an operator-approved registry revision. An approved record cannot override contradictory current provider evidence.

## Add Tickers integration

Add Tickers now obtains a structured identity result before eligibility classification. Existing quarterly-history, market, classification, security-type, fiscal-integrity, taxonomy, and full V2/RP/RV guards remain independent.

Candidate identity mutation has three explicit actions:

- `UPDATE_CURRENT_TICKER`: preserve `company_id` and `security_id`, close the old alias interval, add the new current alias, and update provider ticker text.
- `CREATE_SECURITY`: reuse a proven company only, allocate a new `security_id`, and never infer same security from CIK.
- `CREATE_COMPANY_AND_SECURITY`: allocate both identities for an unambiguous new provider identity.

`PROPOSED` review records cannot reach these actions. Identity resolution does not bypass usable ARQ history: an identity-resolved ticker without ARQ evidence remains `NO_USABLE_QUARTERLY_HISTORY`.

Exchange evidence is explicit:

- `EXCHANGE_CONFIRMED_SUPPORTED`
- `EXCHANGE_CONFIRMED_UNSUPPORTED`
- `EXCHANGE_UNKNOWN`
- `EXCHANGE_FROM_APPROVED_REVIEW`

Missing metadata now reports `EXCHANGE_UNKNOWN`; it is not mislabeled as an incompatible exchange.

## Read-only Administration Preview

`RESOLVE_TICKER_IDENTITY` is available through the Admin service/UI and CLI:

```bash
python3 -m rawcandle.cli.run_fundamentals_admin_identity_preview DRK KRSA PSQL QVCG
```

It accepts at most 25 tickers, opens source databases read-only, produces self-contained JSON and Markdown evidence, and exposes no Test or Production action.

## Four researched cases

Live read-only Preview: `20260921T075259Z_resolve_ticker_identity_161be72e25d5`.

| Ticker | Resolver result | Company continuity | Security continuity | Deterministic? | Review needed? |
| --- | --- | --- | --- | --- | --- |
| DRK | `IDENTITY_REVIEW_REQUIRED` | Same company proposed | Same security proposed | No | Yes |
| KRSA | `IDENTITY_REVIEW_REQUIRED` | Same legal issuer after combination proposed | Successor security proposed | No | Yes |
| PSQL | `IDENTITY_REVIEW_REQUIRED` | New public issuer proposed | New security proposed | No | Yes |
| QVCG | `IDENTITY_REVIEW_REQUIRED` | Successor company proposed | New security proposed | No | Yes |

All four exact tickers are absent from the current local Sharadar metadata snapshot. Accordingly, none is forced through a deterministic path. The registry entries remain `PROPOSED`.

### DRK

The current local snapshot has no DRK provider row and no canonical ANY/167235 mapping. SEC evidence identifies Sphere 3D, CIK `0001591956`, and describes DRK as a reserved symbol, but the September 14 filing still says ANY remained the current symbol pending Nasdaq procedures. The hypothesis is a same-security rename, but the effective transition is not established by current local authoritative state.

Evidence: https://www.sec.gov/Archives/edgar/data/1591956/000121390026099458/ea030536701ex99-1.htm

### KRSA

The current local snapshot has no KRSA provider row. CIK `0001755237` resolves to canonical company `627` and CYCN security `628`, proving a company-level link. SEC and Nasdaq evidence show a merger/change of control, reverse split, symbol change, and new CUSIP. V1 therefore proposes `REORGANIZATION_SUCCESSOR`, not an automatic same-security merge.

Evidence:

- https://www.sec.gov/Archives/edgar/data/1755237/000119312526389318/d178159d8k.htm
- https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-648

### PSQL

Pasqal Holding SA, CIK `0002119292`, became public through a multi-step combination in which BBCQ merged into a French merger subsidiary and Legacy Pasqal then merged into the survivor. PSQL is proposed as `BUSINESS_COMBINATION_NEW_SECURITY`; BBCQ is not treated as the same company or security merely because it was the SPAC predecessor.

Evidence:

- https://www.sec.gov/Archives/edgar/data/2119292/000121390026094393/ea0303667-6k_pasqal.htm
- https://www.sec.gov/Archives/edgar/data/2119292/000121390026098421/ea0304681-01.htm

### QVCG

SEC evidence says old parent equity was cancelled for no consideration. Former subsidiary QVC, Inc., CIK `0001254699`, was renamed QVC Group, Inc. and issued the new post-emergence common stock. V1 proposes `REORGANIZATION_SUCCESSOR` with a successor company and new security; old QVCAQ/QVCBQ equity is not aliased onto QVCG.

Evidence:

- https://www.sec.gov/Archives/edgar/data/1254699/000110465926107125/tm2625133-1_s1.htm
- https://investors.qvcgrp.com/investors/stock-data/faq

## Tests and safety evidence

Focused production-shaped fixture coverage proves:

- exact existing security creates no identity;
- same permaticker transition preserves company/security IDs and alias history;
- same CIK with a different permaticker creates a new security under the same company;
- ticker reuse does not join through historical ticker text;
- provider metadata absent fails closed without approved review;
- `APPROVED` is consumed generically and `PROPOSED` is not;
- provider/review conflicts fail closed;
- missing CIK does not block otherwise valid identity;
- identity authority and usable ARQ history remain independent;
- Preview leaves all source database mtimes unchanged;
- Admin UI exposes Preview only for identity resolution.

Safety summary:

- Live databases changed: `NO`
- Live Add Tickers executed: `NO`
- Scheduler changed: `NO`
- Candidate databases created: `NO`
- Phase-owned large temporary files remaining: `NO`
