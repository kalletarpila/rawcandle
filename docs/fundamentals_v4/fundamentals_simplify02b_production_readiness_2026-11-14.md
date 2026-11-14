# SIMPLIFY-02B — one-time universe activation readiness

**READY_FOR_AUTHORIZED_ACTIVATION.** Production activation was not performed.
Accepted implementation: `160fcf30a99a32bfbf3d480187d24db497eeca89`;
branch `chore/ignore-backups`, no conflicting source edits. Only this report is
changed/committed. Source correction is unnecessary: the native Python entry point
already accepts exact nonblocking B/A confirmation. The Admin service has no
universe-specific convenience entry; no new UI, receipt or issuer is needed.

## Current production and reviewed change

Fresh native read-only authority/role verification and source staging used the
existing admin/scheduler leases and protected taxonomy reader. Observed A:
`current_rebuild_2a684ef130c6a540de4adc560ab171ad`. Installed universe:
`3b8121b74c852f08575fa1e2b70004e6`. Watermark `2026-10-28`. Journal remains
`COMPLETED / PASSED / NOT_REQUIRED`; Fundamentals is disabled, SNAPSHOT_V1 /
FULL_WORKFLOW. The native leases were acquired without conflict and released;
there was no human/network wait under them and no scheduler reconfiguration.

All three financial role SQLite integrity/manifest hashes were verified natively.
The isolated A manifest SHA and role hashes equal the live verified A exactly.
Review queue content binding, identity registry, financial files, active manifest,
journal and scheduler configuration were rechecked unchanged after the exercise.
Market/taxonomy were bound at their current protected source stage, not to obsolete
nightly whole-file hashes. The financial as-of remains the accepted analysis date
2026-10-30. No financial freshness repair is claimed.

Exact approved company / representative / security / Sharadar selections:

| Company | Representative | Security | Sharadar | Companion security |
| ---: | --- | ---: | --- | ---: |
| 442 | CENT | 442 | 197778 | 443 |
| 627 | CYCN | 628 | 111101 | 2558 |
| 886 | FOXA | 888 | 111125 | 887 |
| 912 | FWONA | 914 | 191707 | 915 |
| 969 | GOOGL | 973 | 195146 | 972 |
| 1272 | LBTYA | 1277 | 191556 | 1278 |
| 1296 | LILA | 1302 | 121104 | 1303 |
| 1307 | LLYVA | 1314 | 640301 | 1315 |
| 1407 | METC | 1415 | 124161 | 1416 |
| 1600 | NWSA | 1610 | 191637 | 1609 |
| 2243 | UAA | 2254 | 194726 | 2253 |
| 2441 | ZG | 2458 | 179220 | 2452 |

No admission or identity/model/price/share-count/P/B changes were made. KRSA's
current 160 provider observations and lack of fabricated incoming mapping remain
protected. Provider and analysis bytes remain exact OLD, proving preservation of
PSQL/QVCG and inactive-company analysis history as well. Native canonical checks
compare all non-universe tables and schema; companion identities/aliases, unrelated
members and accepted approvals remain unchanged. There is no duplicate company
financial history or approval transfer.

## Actual current-OLD disposable exercise

B ID: `20261114T124951Z_refresh_fundamentals_cce2b9c73301_universe_reconciliation_8707af9f`.
Test-installed universe: `2113bb9da2e5d620a8aa4de67c53f208`;
content fingerprint `84092995b0a40a7a26b959c1bbd5244b9cd25414fd5b87338c8f6d677083a59c`.

| B role | Verified SHA-256 |
| --- | --- |
| provider | `14a032489577c079607e16986380076986ab8206ed1d96aa135700499432de4f` |
| canonical | `519315eea7423f34b9756743d165d3ac93dcefd850f94495605fb5e045f05ae9` |
| analysis | `6feb14748b4088096d96287d7f3b1c812faed4dc8e2352a81b390d8b86d11d8f` |

The accepted native operation built B from a real isolated copy of current A,
applied all twelve choices, verified complete B and economic/input equivalence,
called the exact confirmation callback once, activated the copy's pointer, passed
native postflight and completed its journal. **COMPLETED / PASSED**. A subsequent
explicit disposable rollback used the same native journal and retained A and
returned **RECOVERED**, with original A active again. Native recovery removed the
test B; its exact manifest/hashes and verification remain in the evidence. This
B is test evidence, not a production candidate or activation authorization.

Preparation through B's native manifest timestamp: **113.143 s** (native
start timestamp has one-second resolution). Full prepare/publish/postflight:
**151.144 s**. Initial production inspection/source isolation:
**90.273 s**. No timing is inferred from small fixtures.

**Additional OLD rollback copies: 0.** The isolated test requires one initial A
role set: three files / 2,630,053,888 bytes. The B role set is necessary candidate
construction. A is reused directly for rollback; no backup role DBs were created.
Market used a native compact bundle instead of another full live market copy.

The closed native owned-copy environment requires its source paths beneath its
own root. To preserve that boundary, taxonomy used the existing full SQLite
backup fallback: **14,471,372,800 bytes**, one isolation source
copy, not an OLD rollback backup. No unsafe hardlink/live-WAL alias or new source
projection was introduced. Production activation uses protected direct taxonomy
and needs no such isolation source copy. Retained task storage after rollback:
**18,016,576,586 logical bytes**; observed sample while B existed:
20,662,356,692 bytes (continuous peak was not measured). Retain owned copies through
operator review; retire only after evidence is accepted and no recovery obligation
remains. No unrelated cleanup occurred. Initial free capacity exceeded the bounded
22 GB estimated exercise requirement.

## Focused tests and existing evidence

**14 PASS**, zero failures/errors/skips, JUnit **33.246 s**, socket
attempts **0**. This runs the twelve targeted SIMPLIFY-02 exact-confirmation,
corruption, review/configuration drift, no-copy, C protection and legacy restore
cases, plus two interrupted native activation/recovery cases. The accepted
153-case SIMPLIFY-02 evidence covers the unchanged additional regressions and is
reused; it was not rerun as a ritual. No full suite or live acquisition ran.

## Exact existing operator invocation — future authorization only

Entry: `rawcandle.fundamentals.admin.universe_reconciliation.run_reconciliation`
with `SnapshotEnvironment()` and `confirm_candidate(binding)`.
The reviewable input plan is
`temp/fundamentals_simplify02b/activation_plan.json`; it is descriptive input, not
an authorization token. A later explicitly authorized operator run can use:

```python
# Run only under a SEPARATE explicit production activation authorization.
plan = json.loads(plan_path.read_text())
env = SnapshotEnvironment()
def confirm_exact(binding):
    assert binding['old'] == plan['expected_old']
    assert binding['approval'] == plan['expected_approval']
    assert binding['universe'] == plan['reviewed_universe']
    assert binding['authority'] == plan['expected_authority']
    assert binding['candidate']['generation_id'] == binding['operation_id']
    for role in ('provider', 'analysis'):
        assert binding['candidate']['role_verification'][role]['sha256'] == plan['expected_old']['role_hashes'][role]
    # B's exact manifest/hashes are already natively verified; returning this
    # exact detached binding confirms that actual B against A. No input/wait.
    return binding
run_reconciliation(env, plan['decisions'],
    approval_reference=plan['approval_reference'],
    expected_approval=plan['expected_approval'], expected_code=plan['expected_code'],
    expected_old=plan['expected_old'], expected_universe=plan['expected_universe'],
    confirmation=CONFIRM, confirm_candidate=confirm_exact,
    production_intent=True, stop_after='publish')
```

Imports are the native `SnapshotEnvironment`, `run_reconciliation` and `CONFIRM`
above, plus `json`/`Path`. The callback is preconfigured from the separately
approved operation plan, not an interactive prompt held under a writer lock.
It was exercised with equivalent native copy authority; production uses the
recorded live authority. Native code rechecks exact B role bytes and required
inputs after the callback before journal/activation. The existing writer lease,
expected A check and journal provide concurrency/rollback; no additional approval
artifact is created.

Live B is prepared afresh and has its own operation ID and canonical physical
hash; the removed disposable B must not be reused as authority. Required identity,
review, configuration, universe or code drift stops the planned operation. Refresh
this plan/readiness if its required authority changes. Market/taxonomy dependencies
are staged and verified freshly within that operation; their old whole-file hashes
are not frozen by this plan. A changed reviewed universe identity also needs a
fresh plan, not forced values. Native postflight remains mandatory.

## Safety and next action

No production DB/review writes, live activation, UPDATE, Sharadar/SEC calls,
watermark movement, scheduler modification or financial policy relaxation.
Production A and universe are unchanged. All native test writes target owned
isolation paths. No source/test correction is required and no implementation
blocker remains in this tested scope.

**Next action:** separately authorize this one-time identity-only reconciliation,
then recheck the plan's current A/authority and invoke the native function above.
Do not start financial acquisition/Phase 3E as part of that activation.

Evidence: `temp/fundamentals_simplify02b/exercise_result.json`, `activation_plan.json`,
`focused.xml` and native operation records under
`temp/fundamentals_simplify02b/isolated/admin_runs/20261114T124951Z_refresh_fundamentals_cce2b9c73301_universe_reconciliation_8707af9f/`.
No runtime DB, copy, log, plan, receipt or generated evidence is committed. Only
this report is committed; Push: NO.
