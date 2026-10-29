# Persistent OPEN provider-history guidance — 2026-10-29

Task: `FUNDAMENTALS-REVIEW-UX-NEXT-ACTION-GUIDANCE`.

This small follow-up to the action-first UI adds a staged operator path where the previous wording offered Wait or Retry without clearly explaining their order or what to investigate if the exception persists. It changes only the existing shared presentation helper and its tests; rendering, controls, backend workflows, and history grouping are reused.

For an OPEN `TRUE_SOURCE_REMOVAL` case with explicit backend retained-history ineligibility and an interior-removal or same-fiscal-replacement reason, the row now shows:

1. Recommended now: Wait for Providers, if that existing action is allowed.
2. After later provider/source refresh: Retry reevaluation after source data changes, if that existing action is allowed.
3. If still unresolved: investigate source history manually. For a same-fiscal replacement, compare the old and new source binding and financial payload before any retained-history or repair decision.

The persistence step is conditional operator advice. No age threshold, persistent-state detection, deep-review state, automatic escalation, repair decision, or new action is introduced. Existing approval/pending paths retain priority. WAITING_PROVIDER, RETRY_REEVALUATION, resolved/history, and unrelated classifications do not receive this OPEN guidance.

## Examples and safety

FDX's structured `INTERIOR_SOURCE_KEY_REMOVAL` reason selects the staged wait/refresh/retry/manual-investigation advice. RRC's `SAME_FISCAL_SOURCE_KEY_REPLACEMENT` selects the stronger binding/payload comparison advice. If both reason codes occur, the replacement investigation advice takes precedence while the original reason and all reason codes remain visible through the existing row/details/tooltips.

Selection uses structured status, classification, eligibility, action availability, and reason codes. There is no ticker-specific production logic or prose parsing. Retained-history approval remains hidden/blocked by the same backend eligibility. The helper does not add allowed actions, mutate its input, record a review decision, change state, register an investigation, or invoke a workflow. No provider-history/source-removal, P/B policy/publication, scheduler, or financial semantics changed.

## Focused validation

**148 tests passed in 10.90 seconds** across:

```text
tests/test_fundamentals_review_action_first.py
tests/test_fundamentals_admin_ui.py
tests/test_fundamentals_admin_refresh_review_queue.py
```

Nine additional parameterized cases cover the two staged paths with a generic unrelated ticker, replacement priority and preservation of reason evidence, waiting/pending/terminal exclusion, each backend-blocked Wait/Retry action, unchanged approval/pending paths, and rendering without mutations. Existing UI confirmation, history separation, zero-state, action availability, and review queue regressions also passed. The full suite was not run.

## Current-state replay

The read-only replay renders real Flet controls with real backend read methods, startup recovery disabled, and mutation methods replaced by failing guards. It verifies FDX/RRC guidance, blocked approval and unchanged Wait/Retry availability, six resolved provider rows in collapsed history, and 13 terminal ownership rows in collapsed history. P/B remains `No action required`, automatic/manual/deep 0/0/0, with V1 enabled.

Runtime/source fingerprints are compared against a fresh baseline and again after rendering; the retained backup inventory is also compared. Local evidence is excluded from the commit under `temp/fundamentals_review_guidance_20261029/`.

Result: **PASS**. Both current OPEN examples rendered the expected staged wording with approval still unavailable. History remained six resolved provider rows and 13 terminal ownership rows. The complete captured runtime/source baseline was unchanged, and all 53 retained backup files were unchanged. Active generation remained `pb_ownership_719201a6f6f4497bb6a3e1ada35b81b6`, watermark `2026-10-28`; journal/postflight/recovery remained COMPLETED/PASSED/NOT_REQUIRED.

The initial attempt to use the production preflight's exclusive scheduler lock stopped before rendering because an independent Stockcore Yahoo run held a shared/read lock. The read-only replay instead excludes admin/production writers with the existing locks and holds a compatible shared scheduler read lock. It invokes no mutating workflow or production gate and does not stop, release, or override the other process's lock. Source/runtime equality checks guard the read-only inspection against drift.

Validation covers the headless Flet control tree rather than a desktop screenshot. No live workflow, approval, publication, review write, scheduler config change, runtime journal/generation change, financial DB write, or backup deletion is performed. Runtime, temporary evidence, OHLCV/research artifacts, and unrelated worktree files remain outside the source commit.
