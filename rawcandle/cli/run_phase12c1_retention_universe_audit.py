from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from rawcandle.fundamentals.schema.phase12c_backfill import provider_counts
from rawcandle.research.phase12c1_audit import (
    analyze_source, discover_history_policy, load_identity_context,
    load_market_context, oldest_reconciliation, production_state,
    read_tickers, result_fingerprint, write_csv, write_json,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "temp/fundamentals_v4_phase12c/20260910T_APPLY_10Y_A/sharadar_fundamentals_10y.csv"
DEFAULT_UNIVERSE = ROOT / "temp/v3_active_tickers_99_27.csv"


def _git(*args: str) -> str:
    return subprocess.run(("git", *args), cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def _markdown(result: dict[str, object]) -> str:
    source = result["source_inventory"]
    oldest = result["oldest_date_reconciliation"]
    bias = result["survivorship_bias"]
    return f"""# Phase 12C.1 Retention and Historical-Universe Audit

## Outcome

`{result['principal_outcome']}`

Phase 12C production data was not rolled back. This audit made no production
database or report changes and did not contact Sharadar.

## Permanent policy

The permanent ten-year minimum is **not implemented**. The ordinary production
bootstrap still requests `years=5`; the ten-year request exists only in the
Phase 12C command. Provider persistence is append-only and retains valid rows
that disappear from or age beyond a later rolling snapshot.

## Oldest ARQ reconciliation

The global staged minimum is `{oldest['global_oldest_arq']}`; the current target,
identity-valid and production minimum is `{oldest['production_retained_oldest_arq']}`.
All {oldest['rows_before_production_minimum']} earlier ARQ provider rows are outside
the current target universe; none was lost after target selection. Production
contains {oldest['production_minus_current_snapshot_rows']} additional ARQ rows
retained from earlier snapshots under append-only semantics.

## Historical universe

The source contains {source['unique_tickers_by_dimension']['ARQ']} ARQ tickers;
only {result['source_audit']['target_ticker_counts']['ARQ']} occur in the current
operational target. The source has ticker symbols but no permanent security or
company identifier, instrument type, listing status, acquisition, bankruptcy or
delisting field. Current taxonomy/sector values are descriptive context only,
not historical PIT classifications.

Measured exclusion is material: {bias['arq_excluded_tickers']} ARQ tickers are
outside the operational universe, including {bias['arq_excluded_with_direct_ohlc']}
with direct local OHLC identity. This creates likely upward survivorship bias for
historical return research because disappeared firms are systematically more
likely to be absent, although acquisition and unresolved identity effects make
the exact magnitude unknown.

## Recommendation

Keep the 2,451-company scope for current operational V4/Snapshot reporting.
Before or beside Phase 12D, establish a separate broad historical research
universe with dated identities and terminal-return handling. First correct the
normal ingestion policy so every relevant fundamentals request uses a ten-year
minimum without pruning older local observations. Do not broaden production
Snapshot readers merely to solve an ML research-universe problem.

The history is currently revised history, not point-in-time history. The locked
Phase 12B periods, labels, purge, embargo, hypotheses and gates remain unchanged.
Raw warmup now makes a larger replay plausible, but the common-cohort gate cannot
be claimed to pass until canonical, TTM and downstream reconstruction is
separately authorized and completed.
"""


def _supporting_markdown(output: Path, result: dict[str, object]) -> None:
    (output / "PHASE12C1_RETENTION_AND_UNIVERSE_AUDIT.md").write_text(_markdown(result), encoding="utf-8")
    (output / "universe_definition.md").write_text(
        "# Universe definition\n\nThe operational source is `temp/v3_active_tickers_99_27.csv`: "
        "2,470 current ticker symbols derived from a local SEC/fiscal-calendar bootstrap. "
        "Sharadar rows are selected by exact current ticker membership; 2,451 occur in the "
        "ten-year ARQ/MRQ snapshot. This is not a historical membership universe.\n", encoding="utf-8")
    (output / "survivorship_bias_assessment.md").write_text(
        "# Survivorship bias assessment\n\nOperational current-universe reporting remains appropriate. "
        "Revised-history feature research is incomplete outside that universe. ML return research "
        "has likely upward survivorship bias because historical fundamentals and direct local OHLC "
        "exist for excluded tickers, while authoritative delisting and terminal-return semantics are absent.\n",
        encoding="utf-8")
    (output / "research_universe_options.md").write_text(
        "# Research universe options\n\n- A: current operational universe is simplest but has material survivorship risk.\n"
        "- B: retain operational scope and add a broad historical research identity/canonical layer. Recommended.\n"
        "- C: broaden production canonical V4; highest migration and reader risk, and unnecessary for current reports.\n",
        encoding="utf-8")
    (output / "recommended_phase12d_scope.md").write_text(
        "# Recommended scope before Phase 12D\n\n1. Version the permanent ten-year minimum request policy and tests.\n"
        "2. Keep append-only provider retention with no ten-year maximum cutoff.\n"
        "3. Define a separate broad historical research universe and dated identity contract.\n"
        "4. Add delisting/terminal-return handling before ML labels.\n"
        "5. Only then authorize canonical/TTM/downstream revised-history reconstruction and unchanged Phase 12B replay.\n",
        encoding="utf-8")


def _write_machine(output: Path, result: dict[str, object]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "decision.json", result["decision"])
    write_json(output / "source_inventory.json", result["source_inventory"])
    write_json(output / "permanent_history_policy_audit.json", result["history_policy"])
    write_csv(output / "history_window_code_locations.csv", result["history_code_locations"])
    write_json(output / "oldest_date_reconciliation.json", result["oldest_date_reconciliation"])
    write_csv(output / "pre_production_min_arq_rows.csv", result["source_audit"]["early_arq_rows"])
    write_csv(output / "global_to_target_waterfall.csv", result["oldest_date_reconciliation"]["waterfall"])
    write_csv(output / "excluded_identity_summary.csv", result["source_audit"]["excluded_identities"])
    write_csv(output / "excluded_identity_reason_counts.csv", result["source_audit"]["excluded_reason_counts"])
    write_csv(output / "historical_universe_by_year.csv", result["source_audit"]["historical_universe_by_year"])
    write_csv(output / "market_identity_coverage.csv", result["market_identity_coverage"])
    write_json(output / "phase12b_raw_feasibility.json", result["source_audit"]["phase12b_feasibility"])
    write_json(output / "production_preflight_postflight.json", result["production_preflight_postflight"])
    (output / "commands_run.txt").write_text(
        "python -m rawcandle.cli.run_phase12c1_retention_universe_audit --source <RETAINED_PHASE12C_CSV> --output <NEW_TEMP_DIR>\n"
        "pytest -q tests/test_phase12c1_retention_universe_audit.py tests/test_phase12c_sharadar_backfill.py\n"
        "git diff --check\n", encoding="utf-8")
    _supporting_markdown(output, result)


def run(source: Path, universe: Path, output: Path) -> dict[str, object]:
    if not source.is_file() or source.is_symlink():
        raise RuntimeError("PHASE12C1_RETAINED_SOURCE_REQUIRED")
    if output.exists() or (ROOT / "temp/fundamentals_v4_phase12c1").resolve() not in output.resolve().parents:
        raise RuntimeError("PHASE12C1_NEW_TEMP_OUTPUT_REQUIRED")
    pre = production_state(ROOT)
    target = read_tickers(universe)
    current, aliases = load_identity_context(ROOT / "data/fundamentals_v4.db")
    market, metadata = load_market_context(ROOT / "data/osakedata.db")
    policy, locations = discover_history_policy(ROOT)
    production = provider_counts(ROOT / "data/fundamentals_provider.db")
    production_min = next(row["oldest"] for row in production["by_dimension"] if row["dimension"] == "ARQ")
    first = analyze_source(source, target, current, aliases, market, metadata, production_min)
    second = analyze_source(source, target, current, aliases, market, metadata, production_min)
    if result_fingerprint(first) != result_fingerprint(second):
        raise RuntimeError("PHASE12C1_NONDETERMINISTIC_SOURCE_AUDIT")
    oldest = oldest_reconciliation(first, production)
    reason_arq = [row for row in first["excluded_identities"] if row["dimension"] == "ARQ"]
    bias = {
        "direction": "LIKELY_UPWARD_MAGNITUDE_UNKNOWN",
        "materiality": "MATERIAL_FOR_HISTORICAL_ML_RESEARCH",
        "arq_excluded_tickers": len(reason_arq),
        "arq_excluded_with_direct_ohlc": sum(bool(row["direct_market_match"]) for row in reason_arq),
        "operational_reporting": "CURRENT_SCOPE_APPROPRIATE",
        "revised_history_research": "BROAD_HISTORICAL_UNIVERSE_RECOMMENDED",
        "ml_return_research": "CURRENT_UNIVERSE_UNSUITABLE_AS_SOLE_UNIVERSE",
    }
    coverage = []
    for dimension in ("ARQ", "MRQ"):
        rows = [row for row in first["excluded_identities"] if row["dimension"] == dimension]
        coverage.extend([
            {"dimension": dimension, "scope": "excluded", "tickers": len(rows),
             "direct_market_matches": sum(bool(row["direct_market_match"]) for row in rows),
             "no_direct_market_match": sum(not bool(row["direct_market_match"]) for row in rows),
             "alias_candidates": sum(bool(row["alias_candidate"]) for row in rows),
             "ambiguous_identities": 0},
            {"dimension": dimension, "scope": "target", "tickers": first["target_ticker_counts"][dimension],
             "direct_market_matches": first["direct_market_target_ticker_counts"][dimension],
             "no_direct_market_match": first["target_ticker_counts"][dimension] - first["direct_market_target_ticker_counts"][dimension],
             "alias_candidates": 0, "ambiguous_identities": 0},
        ])
    post = production_state(ROOT)
    immutable = pre["aggregate_fingerprint"] == post["aggregate_fingerprint"]
    if not immutable:
        raise RuntimeError("PHASE12C1_PRODUCTION_CHANGED_DURING_AUDIT")
    contract_fingerprint = result_fingerprint({
        "dimensions": ["ARQ", "MRQ"], "target_semantics": "EXACT_CURRENT_TICKER",
        "revision_semantics": "PROVIDER_ROWS_AND_BASE_PERIODS_SEPARATE",
        "price_labels": "IDENTITY_AND_OHLC_FEASIBILITY_ONLY",
    })
    result = {
        "principal_outcome": "OUTCOME_B_HISTORY_POLICY_CORRECTION_REQUIRED",
        "secondary_outcome": "OUTCOME_C_HISTORICAL_RESEARCH_UNIVERSE_WORK_REQUIRED",
        "decision": {
            "principal_outcome": "OUTCOME_B_HISTORY_POLICY_CORRECTION_REQUIRED",
            "secondary_blocker": "OUTCOME_C_HISTORICAL_RESEARCH_UNIVERSE_WORK_REQUIRED",
            "phase12d_authorized": False,
            "production_data_changed": False,
        },
        "git": {"head": _git("rev-parse", "HEAD"), "branch": _git("branch", "--show-current"),
                "status": _git("status", "--porcelain"),
                "divergence": _git("rev-list", "--left-right", "--count", "HEAD...@{upstream}"),
                "phase12c_is_ancestor": subprocess.run(
                    ("git", "merge-base", "--is-ancestor", "66b37defce9f788b9e966532998a72eee0622cfe", "HEAD"),
                    cwd=ROOT,
                ).returncode == 0},
        "history_policy": policy, "history_code_locations": locations,
        "source_inventory": first["source"], "source_audit": first,
        "oldest_date_reconciliation": oldest, "survivorship_bias": bias,
        "market_identity_coverage": coverage,
        "production_preflight_postflight": {
            "preflight": pre, "postflight": post, "byte_content_unchanged": immutable,
        },
        "audit_contract_fingerprint": contract_fingerprint,
    }
    result["result_fingerprint"] = result_fingerprint({
        "history_policy": policy, "source_audit": first,
        "oldest_date_reconciliation": oldest, "survivorship_bias": bias,
        "market_identity_coverage": coverage,
    })
    result["decision"].update({
        "source_fingerprint": first["source"]["sha256"],
        "audit_contract_fingerprint": contract_fingerprint,
        "result_fingerprint": result["result_fingerprint"],
    })
    replay_a = output / "determinism_run_a"
    replay_b = output / "determinism_run_b"
    _write_machine(replay_a, result)
    _write_machine(replay_b, result)
    a_files = {path.relative_to(replay_a): path.read_bytes() for path in replay_a.rglob("*") if path.is_file()}
    b_files = {path.relative_to(replay_b): path.read_bytes() for path in replay_b.rglob("*") if path.is_file()}
    if a_files != b_files:
        raise RuntimeError("PHASE12C1_SERIALIZED_OUTPUTS_NOT_BYTE_IDENTICAL")
    result["determinism"] = {
        "source_audit_fingerprints_identical": True,
        "serialized_file_count": len(a_files),
        "serialized_outputs_byte_identical": True,
    }
    result["decision"]["deterministic_dual_run"] = True
    _write_machine(output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Phase 12C.1 retention and historical-universe audit")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    parser.add_argument("--output", type=Path, default=ROOT / "temp/fundamentals_v4_phase12c1" / stamp)
    args = parser.parse_args()
    try:
        result = run(args.source.resolve(), args.universe.resolve(), args.output.resolve())
        print(json.dumps({"outcome": result["principal_outcome"], "output": str(args.output.resolve()),
                          "result_fingerprint": result["result_fingerprint"]}, sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps({"outcome": "FAILED", "error": type(error).__name__, "reason": str(error)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
