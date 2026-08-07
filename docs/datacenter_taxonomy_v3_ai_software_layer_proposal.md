# Datacenter Taxonomy V3 AI Software Layer Proposal

## Scope

This is a structural taxonomy draft/proposal only. It does not activate
`DC_TAXONOMY_FULL_V3`, does not run production taxonomy-change execution, and
does not mutate production databases, scheduler config, watchlists, watermarks,
EC state, or report outputs.

Base taxonomy file:

```text
data/datacenter_taxonomy_full_v2_1.csv
```

Draft taxonomy artifacts:

```text
temp/datacenter_taxonomy_v3_ai_software_layer/datacenter_taxonomy_full_v3.csv
temp/datacenter_taxonomy_v3_ai_software_layer/change_log.csv
temp/datacenter_taxonomy_v3_ai_software_layer/added_tickers.csv
temp/datacenter_taxonomy_v3_ai_software_layer/changed_memberships.csv
temp/datacenter_taxonomy_v3_ai_software_layer/structural_changes.csv
temp/datacenter_taxonomy_v3_ai_software_layer/validation_summary.json
```

## New Structure

New layer:

```text
AI software & data workloads
```

New subindustries:

```text
Enterprise AI operating platforms
AI data cloud / vector data platforms
AI observability / agent operations
Agentic automation / workflow AI
AI edge delivery / inference gateways
Vertical AI applications / monetization engines
```

## Primary Memberships

Enterprise AI operating platforms:

```text
CORE: PLTR, AI
EXTENDED: IBM
WATCH_ONLY: BBAI
```

AI data cloud / vector data platforms:

```text
CORE: SNOW, MDB, ESTC
EXTENDED: CFLT, TDC
WATCH_ONLY: none
```

AI observability / agent operations:

```text
CORE: DDOG, DT
EXTENDED: none
WATCH_ONLY: none
```

Agentic automation / workflow AI:

```text
CORE: NOW, CRM, PATH
EXTENDED: TEAM, GTLB, MNDY
WATCH_ONLY: none
```

AI edge delivery / inference gateways:

```text
CORE: NET
EXTENDED: AKAM
WATCH_ONLY: FSLY
```

Vertical AI applications / monetization engines:

```text
CORE: APP
EXTENDED: ADBE, TEM, DUOL, UPST
WATCH_ONLY: SOUN
```

## Entity And Membership Summary

New ticker entities:

```text
ADBE, AI, AKAM, APP, BBAI, CFLT, CRM, DUOL, FSLY, GTLB, IBM, MDB,
MNDY, NET, PATH, PLTR, SOUN, TDC, TEAM, TEM, UPST
```

Existing tickers that received new primary memberships:

```text
SNOW: Operations / Observability / ITSM / data platform
  -> AI software & data workloads / AI data cloud / vector data platforms
ESTC: Operations / Observability / ITSM / data platform
  -> AI software & data workloads / AI data cloud / vector data platforms
DDOG: Operations / Observability / ITSM / data platform
  -> AI software & data workloads / AI observability / agent operations
DT: Operations / Observability / ITSM / data platform
  -> AI software & data workloads / AI observability / agent operations
NOW: Operations / Observability / ITSM / data platform
  -> AI software & data workloads / Agentic automation / workflow AI
```

Existing tickers that kept their current primary memberships and received new
secondary memberships:

```text
MSFT: AI software & data workloads / Agentic automation / workflow AI / EXTENDED
GOOGL: AI software & data workloads / AI data cloud / vector data platforms / EXTENDED
AMZN: AI software & data workloads / AI edge delivery / inference gateways / EXTENDED
ORCL: AI software & data workloads / AI data cloud / vector data platforms / EXTENDED
PANW: AI software & data workloads / AI observability / agent operations / EXTENDED
FTNT: AI software & data workloads / AI edge delivery / inference gateways / EXTENDED
CRWD: AI software & data workloads / AI observability / agent operations / EXTENDED
```

New ticker that received both primary and secondary memberships:

```text
GTLB:
  primary = AI software & data workloads / Agentic automation / workflow AI / EXTENDED
  secondary = AI software & data workloads / AI observability / agent operations / EXTENDED
```

Secondary memberships skipped:

```text
none
```

Intentionally excluded tickers:

```text
AAPL, TSLA, META, NFLX, SHOP, UBER, ABNB, SEZL, RDDT, HOOD
```

The validation verified that none of the excluded tickers were added to the new
V3 layer and that none were introduced as new ticker entities. `META` already
exists in the base taxonomy under `Cloud / Hyperscalers / cloud demand owners`;
that existing base row was preserved and no V3 AI software membership was added.

## Validation Result

Validation status:

```text
OK
```

Validation facts:

```text
base_row_count=350
draft_row_count=384
new_entity_count=21
new_membership_count=34
changed_primary_membership_count=5
secondary_membership_added_count=8
secondary_membership_skipped_count=0
removed_tickers=[]
removed_layers=[]
removed_subindustries=[]
duplicate_primary_memberships=[]
```

Specific required checks passed:

```text
V3 CSV parses successfully
required columns are present
all six new subindustries exist under the new layer
requested CORE / EXTENDED / WATCH_ONLY primary memberships exist
WATCH_ONLY tickers BBAI, FSLY, SOUN are present
explicitly excluded tickers were not added to the new V3 layer
no accidental unrelated layer/subindustry removals occurred
no existing tickers were deleted
no duplicate primary memberships exist
PLTR is AI software & data workloads / Enterprise AI operating platforms / CORE
```

Ordering rule:

```text
Preserve base CSV row order; append requested V3 primary rows in proposal order,
then requested secondary rows in proposal order.
```

## Change Type

This is a computational taxonomy change because it adds a new layer, adds new
subindustries, adds new memberships, and changes five primary memberships. It
must not be treated as `REPORT_STATUS_ONLY`.

## Later Production Steps

Before activation, a separate production change should:

1. Review and approve the V3 draft CSV and review artifacts.
2. Run the existing taxonomy change planning/preflight flow for
   `DC_TAXONOMY_FULL_V3`.
3. Choose the required structural rebuild path, because this proposal changes
   computational taxonomy structure.
4. Run controlled Datacenter and EC rebuild/revalidation steps according to the
   structural taxonomy-change runbook.
5. Activate `DC_TAXONOMY_FULL_V3` only after validation evidence is complete.
6. Update scheduler config only as part of the later activation step.
