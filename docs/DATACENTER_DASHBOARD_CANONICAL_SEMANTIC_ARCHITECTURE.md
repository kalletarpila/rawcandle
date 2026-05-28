# Datacenter Dashboard Canonical Semantic Architecture

## 1. Purpose

This document defines the future canonical semantic architecture for Datacenter dashboard decision inputs.

Clarifications:

- this document does not implement code
- this document does not switch scheduler source mode
- reports-mode remains the reference and fallback path until factual parity is proven


## 2. Problem Statement

The core architectural problem is not visual dashboard parity. It is factual semantic parity.

Reports-mode and enrichment-mode currently start from similar structured Datacenter source data, but they do not feed identical canonical decision input rows into `datacenter_dashboard_decisions.py`.

Reports-mode includes helper-derived semantic companion rows. Enrichment-mode has historically approximated some of those rows with local mappings and condensed fields.

Because the decision layer receives different semantic inputs, the same-named final fields can differ factually between the two modes.

Affected final fields:

- `pullback_validity`
- `entry_readiness`
- `candidate_priority`
- `candidate_priority_label`


## 3. Architectural Principle

There must be one owner for each semantic layer.

Required ownership model:

- `rolling_5_pullback_state`
  - owned by `analysis/datacenter_indices/rolling5_pullback_classifier.py`

- `rolling_2_sell_pressure_state`
  - should be owned by a future shared rolling 2d sell-pressure helper

- `ma_break_status` / `close_below_ema20` / EMA20 break context
  - should be owned by the MA-break helper

- `freshness_status` / `structure_warning_overrides_bullish_signal` / bullish signal age
  - should be owned by the signal freshness helper

- `pullback_validity`
  - owned only by `dev_tools/datacenter_dashboard_decisions.py`

- `entry_readiness`
  - owned only by `dev_tools/datacenter_dashboard_decisions.py`

- `candidate_priority` / `candidate_priority_label`
  - owned only by `dev_tools/datacenter_dashboard_decisions.py`


## 4. Canonical Data Flow Target

Target flow:

Raw/source DC tables  
→ shared semantic helper layer  
→ canonical `DatacenterDashboardRow` decision input builder  
→ `datacenter_dashboard_decisions.py`  
→ structured dashboard output  
→ `ecosystem_dashboard.db` / HTML

Reports mode:

- may still render `.md` for audit and human review
- should use the same shared helper outputs
- should not be the only machine source of helper semantics

Enrichment mode:

- should consume the same shared helper outputs
- should not approximate helper semantics with separate local heuristics


## 5. Current State by Semantic Family

### A. Rolling5 pullback

- status: shared helper exists
- current file: `analysis/datacenter_indices/rolling5_pullback_classifier.py`
- reports-mode uses it
- enrichment-mode can use it under flag
- still requires canonical row-builder parity

### B. MA-break

- status: not yet canonicalized for enrichment
- reports has helper-style output
- enrichment lacks full helper-output equivalent
- `close_below_ema20` is a symptom, not the full root cause

### C. Signal freshness

- status: not yet canonicalized for enrichment
- reports has helper-style output
- enrichment approximates freshness and structure override semantics

### D. Rolling2 sell-pressure

- status: not yet canonicalized for enrichment
- reports has helper-style output
- enrichment approximates rolling 2d status

### E. Dashboard final decisions

- status: decision layer exists
- it should remain the owner of final fields
- it should not be duplicated in writers


## 6. Anti-Patterns To Avoid

- copying reports algorithms into enrichment as second implementations
- parsing `.md` reports in the production enrichment path
- storing final `pullback_validity` as source of truth before canonical inputs are fixed
- adding one-off tokens without understanding helper ownership
- changing dashboard decision rules to hide input mismatch
- switching scheduler source mode before factual parity is safe


## 7. Factual Parity Acceptance Rule

Scheduler source-mode switch is not safe if same-named final fields differ materially.

Minimum parity fields:

- `pullback_validity`
- `entry_readiness`
- `candidate_priority`
- `candidate_priority_label`

Acceptance condition:

- either these fields match between reports and enrichment for common tickers
- or differences are explicitly renamed or documented as different concepts
- otherwise scheduler switch remains blocked for those fields


## 8. Recommended Implementation Sequence

### DB-19b

- inspect MA-break helper output and exact reusable call path
- read-only source inspection first

### DB-19c

- extract or expose MA-break helper output to the canonical input builder
- no decision rule changes

### DB-19d

- inspect signal freshness helper output and exact reusable call path

### DB-19e

- extract or expose signal freshness helper output

### DB-19f

- inspect rolling 2d sell-pressure helper output and exact reusable call path

### DB-19g

- extract or expose rolling 2d sell-pressure helper output

### DB-19h

- build a canonical `DatacenterDashboardRow` input builder or align reports and enrichment adapters to shared helper outputs

### DB-19i

- rerun factual parity validation and acceptance report


## 9. Immediate Next Step

The next task should be DB-19b:

- read-only inspection of MA-break helper output and callability
- because `close_below_ema20` remains the top symptom but is likely part of broader MA-break helper semantics


## 10. Validation

No tests are required unless code changed accidentally.

Run only:

- `git diff --check`
