# Datacenter Taxonomy V3 AI Software Layer Pre-Activation Audit

## Audit Metadata

Audit date/time:

```text
2026-08-07T18:08:09+03:00
```

Audit scope:

```text
Read-only pre-activation audit of the Datacenter V3 AI software & data workloads structural draft.
No V3 activation, production taxonomy-change execution, production database mutation, scheduler update,
Datacenter report run, Datacenter pipeline run, EC job, market fetch, or full pytest run was performed.
```

Relevant commits:

```text
e53f563 Add Datacenter V3 structural taxonomy draft tooling
520cfbe Preserve existing primaries in V3 taxonomy draft
2139904 Set CORE AI secondary status for anchor tickers
```

## Files Audited

Base taxonomy file:

```text
data/datacenter_taxonomy_full_v2_1.csv
```

V3 draft taxonomy file:

```text
temp/datacenter_taxonomy_v3_ai_software_layer/datacenter_taxonomy_full_v3.csv
```

Supporting draft artifacts:

```text
temp/datacenter_taxonomy_v3_ai_software_layer/change_log.csv
temp/datacenter_taxonomy_v3_ai_software_layer/added_tickers.csv
temp/datacenter_taxonomy_v3_ai_software_layer/changed_memberships.csv
temp/datacenter_taxonomy_v3_ai_software_layer/structural_changes.csv
temp/datacenter_taxonomy_v3_ai_software_layer/validation_summary.json
docs/datacenter_taxonomy_v3_ai_software_layer_proposal.md
```

## Validation Summary

Stored validation summary:

```text
validation_status=OK
base_taxonomy_version=DC_TAXONOMY_FULL_V2_1
draft_taxonomy_version=DC_TAXONOMY_FULL_V3
base_row_count=350
draft_row_count=384
new_entity_count=21
new_membership_count=34
changed_primary_membership_count=0
secondary_membership_added_count=13
secondary_membership_skipped_count=0
removed_tickers=[]
removed_layers=[]
removed_subindustries=[]
changed_primary_memberships=[]
production_activation_performed=false
computational_taxonomy_change=true
```

Independent validator result:

```text
taxonomy_rows=384
unique_tickers=278
layer_count=17
subindustry_count=43
core_rows=242
extended_rows=125
watch_only_rows=17
too_small_rows=0
duplicate_rows=0
validation_status=OK
```

## New Structure

New layer confirmed:

```text
AI software & data workloads
```

Six new subindustries confirmed:

```text
Enterprise AI operating platforms
AI data cloud / vector data platforms
AI observability / agent operations
Agentic automation / workflow AI
AI edge delivery / inference gateways
Vertical AI applications / monetization engines
```

## Primary Membership Policy

Existing base-taxonomy tickers keep their current primary memberships. The audit
confirmed `changed_primary_membership_count=0`, no base tickers were deleted,
and no duplicate primary memberships exist.

New AI software tickers receive primary memberships under the new layer. `PLTR`
is present exactly as required:

```text
PLTR / AI software & data workloads / Enterprise AI operating platforms / CORE / primary
```

## Secondary Membership Policy

The audit confirmed that selected existing base-taxonomy tickers keep their base
primary rows while receiving AI-layer secondary rows.

CORE AI secondary memberships:

```text
SNOW / AI data cloud / vector data platforms / CORE / secondary
ESTC / AI data cloud / vector data platforms / CORE / secondary
DDOG / AI observability / agent operations / CORE / secondary
DT / AI observability / agent operations / CORE / secondary
NOW / Agentic automation / workflow AI / CORE / secondary
```

The retained base primary for each of these five tickers is:

```text
Operations / Observability / ITSM / data platform / CORE / primary
```

EXTENDED AI secondary memberships:

```text
MSFT / Agentic automation / workflow AI / EXTENDED / secondary
GOOGL / AI data cloud / vector data platforms / EXTENDED / secondary
AMZN / AI edge delivery / inference gateways / EXTENDED / secondary
ORCL / AI data cloud / vector data platforms / EXTENDED / secondary
PANW / AI observability / agent operations / EXTENDED / secondary
FTNT / AI edge delivery / inference gateways / EXTENDED / secondary
CRWD / AI observability / agent operations / EXTENDED / secondary
```

The 13th secondary membership is:

```text
GTLB / AI observability / agent operations / EXTENDED / secondary
```

`GTLB` also has a new primary membership in:

```text
AI software & data workloads / Agentic automation / workflow AI / EXTENDED / primary
```

## Final AI Layer Ticker Lists

An asterisk marks a secondary membership; unmarked tickers are primary
memberships.

Enterprise AI operating platforms:

```text
CORE: AI, PLTR
EXTENDED: IBM
WATCH_ONLY: BBAI
```

AI data cloud / vector data platforms:

```text
CORE: ESTC*, MDB, SNOW*
EXTENDED: CFLT, GOOGL*, ORCL*, TDC
WATCH_ONLY: none
```

AI observability / agent operations:

```text
CORE: DDOG*, DT*
EXTENDED: CRWD*, GTLB*, PANW*
WATCH_ONLY: none
```

Agentic automation / workflow AI:

```text
CORE: CRM, NOW*, PATH
EXTENDED: GTLB, MNDY, MSFT*, TEAM
WATCH_ONLY: none
```

AI edge delivery / inference gateways:

```text
CORE: NET
EXTENDED: AKAM, AMZN*, FTNT*
WATCH_ONLY: FSLY
```

Vertical AI applications / monetization engines:

```text
CORE: APP
EXTENDED: ADBE, DUOL, TEM, UPST
WATCH_ONLY: SOUN
```

## Explicit Exclusions

The following tickers were confirmed absent from the new V3 AI layer:

```text
AAPL, TSLA, META, NFLX, SHOP, UBER, ABNB, SEZL, RDDT, HOOD
```

`META` remains present only because it already exists in the base taxonomy; the
audit found no `META` membership under `AI software & data workloads`.

## Risks And Items To Watch

This draft is a computational and structural taxonomy change because it adds a
new layer, six subindustries, 21 new ticker entities, and 34 memberships.
Activation should therefore use the full production taxonomy-change planning,
preflight, rebuild, and validation path rather than a report-status-only path.

Primary membership preservation is intentional. Downstream consumers must be
reviewed for assumptions that a ticker belongs to only one report-relevant
group, because several existing tickers now carry AI-layer secondary memberships
with `CORE` or `EXTENDED` status.

`GTLB` has both a primary and a secondary membership inside the new AI layer.
That is deliberate in the draft, but production review should confirm that
same-layer secondary membership behavior is supported by report generation and
index construction expectations.

## Recommendation

The V3 AI software & data workloads taxonomy draft is ready for production
taxonomy-change planning.

It is not ready for direct activation without the normal structural taxonomy
change workflow. The next step should be production taxonomy-change planning and
preflight for `DC_TAXONOMY_FULL_V3`, followed by controlled rebuild and
validation before any activation.
