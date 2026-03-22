# Final Tier Classification

## Locked Research Summary Version

### Tier 1 - Production-grade structure edges (BullDiv only)

These regions show stable forward return structure and do not benefit from combo confirmation.

#### T1-A

- BullDiv
- `pivot_gap_r3 = 19-22`
- `pivot_drop_pct_r3 = 3-5`
- `rsi = 36-45`

Status:

- production-grade structure edge
- combo neutral or harmful

#### T1-B

- BullDiv
- `pivot_gap_r3 = 8-10`
- `pivot_drop_pct_r3 < 3`
- `rsi > 45`

Status:

- production-grade structure edge
- combo harmful

This is the strongest negative combo-result region observed in the matched comparison.

### Tier 2 - Selective execution-upgrade candidates (shallow stabilization regime)

Structure condition:

- `pivot_gap_r3 = 5-7`
- `pivot_drop_pct_r3 < 3`

Combo confirmation improves entry quality only for specific patterns.

#### T2-A Hammer

- BullDiv
- Hammer
- `gap 5-7`
- `drop < 3`

Status:

- strong execution-upgrade candidate

Evidence summary:

- positive 10d improvement
- positive 20d direction
- positive 30d direction
- sufficiently large sample size
- effect not pattern-neutral across combos

#### T2-B Dragonfly Doji

- BullDiv
- Dragonfly Doji
- `gap 5-7`
- `drop < 3`

Status:

- execution-upgrade candidate (watchlist-strong)

Evidence summary:

- positive 20d evidence
- positive 30d evidence
- smaller sample size than Hammer
- promising but still secondary confidence level

### Tier 3 - Secondary structure zones (BullDiv only)

Valid reversal structure regions with weaker or regime-dependent performance.

#### T3-A

- BullDiv
- `gap 15-22`
- `drop 5-7`
- `rsi 30-36`

Status:

- secondary structure zone

#### T3-B Deep-drop regime

- BullDiv
- `gap 11-18`
- `drop 20-30`
- `rsi 30-36`

Status:

- regime-dependent watchlist

Performance appears sensitive to market environment and historical clustering.

### Tier 4 - Baseline stabilization regime

- BullDiv
- `gap 5-7`
- `drop < 3`
- no combo required

Status:

- baseline stabilization regime
- stable low-amplitude structure edge
- execution-upgrade possible

Optional execution improvements observed:

- Hammer
- Dragonfly Doji

But they are not required for entry validity.

## Locked Structural Interpretation

This statement best matches the current dataset:

- BullDiv defines reversal structure.
- Hammer sometimes improves timing inside shallow stabilization regime.
- Dragonfly Doji may improve timing inside the same regime.
- Combo does NOT generally improve BullDiv entry.

This reflects the outcome of:

- bucket-matched comparison
- event-level deduplication
- combo vs no-combo testing
- pattern-level split inside matched structures

## Explicitly Rejected Hypotheses

These should remain locked as invalidated assumptions:

- any combo improves BullDiv entry
- combo improves gap 19-22 zone
- combo improves gap 8-10 zone
- combo acts as a universal execution layer for BullDiv

Documenting rejected hypotheses is essential for maintaining deterministic signal discipline in RC.
