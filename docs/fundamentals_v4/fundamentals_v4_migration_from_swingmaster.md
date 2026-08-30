# Fundamentals V4 Migration From SwingMaster

RawCandle V4 copies or adapts proven code from SwingMaster, but does not import SwingMaster at runtime.

## Migrated In V4-0C

- `swingmaster/providers/sharadar.py` -> `rawcandle/fundamentals/providers/sharadar.py`
- `swingmaster/cli/run_sharadar_v4_smoke.py` -> `rawcandle/cli/run_sharadar_v4_smoke.py`
- focused Sharadar tests -> `tests/test_fundamentals_v4_sharadar_provider.py`

## Use As Reference

- V3 fiscal identity lessons
- SEC companyfacts parsing details
- EBIT-first TTM behavior
- locked score and lifecycle model fingerprints
- valuation-date behavior

## Do Not Migrate By Default

- Phase 8 repair runners
- fiscal repair queues
- H3 mapping logic
- V3 Q4 repair scripts
- V3 Yahoo fiscal heuristics
- broad SEC reconciliation machinery
- migration-only scripts
- V3 external research packaging

## Preservation Rules

Score and lifecycle migration is not recalibration. Initial RawCandle ports must preserve formulas, thresholds, model versions, and fingerprints until a separate model-change phase approves changes.
