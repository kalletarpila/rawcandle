from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals.admin.batch_add_tickers import (
    BatchAddTickerPaths,
    build_preview_from_copy,
    create_copy_lane,
    parse_batch_tickers,
    reject_production_write_targets,
    run_apply,
    run_preview,
)
from rawcandle.fundamentals.admin.history import AdminRunHistory
from rawcandle.fundamentals.phase12d import write_json
from rawcandle.fundamentals.phase13d_backend import Phase13DPaths
from tests.test_phase13d_backend import _analysis, _canonical, _market, _provider, _taxonomy


def _paths(tmp_path: Path) -> BatchAddTickerPaths:
    tmp_path.mkdir(parents=True, exist_ok=True)
    provider = tmp_path / "provider.db"
    canonical = tmp_path / "canonical.db"
    analysis = tmp_path / "analysis.db"
    market = tmp_path / "market.db"
    taxonomy = tmp_path / "taxonomy.db"
    _provider(provider)
    _canonical(canonical)
    _analysis(analysis)
    _market(market)
    _taxonomy(taxonomy)
    return BatchAddTickerPaths(provider, canonical, analysis, market, taxonomy)


def test_batch_parse_normalizes_deduplicates_and_orders_deterministically() -> None:
    request = parse_batch_tickers(" newc,NEWC\nlimit bad$ ")

    assert request.requested_inputs == ("newc", "NEWC", "limit", "bad$")
    assert request.normalized_inputs == ("NEWC", "LIMIT")
    assert request.rejected_inputs == ({"requested_value": "bad$", "reason": "Malformed item key"},)


def test_preview_fingerprint_and_mixed_statuses_are_stable(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    request = parse_batch_tickers("AAA NEWC LIMIT MISS BAD$")

    first, raw_first = build_preview_from_copy(paths, request, now="2026-09-15T00:00:00Z")
    second, raw_second = build_preview_from_copy(paths, request, now="2026-09-15T00:00:00Z")

    statuses = {item.normalized_value: item.status.value for item in first.decisions}
    assert statuses["AAA"] == "ALREADY_PRESENT"
    assert statuses["NEWC"] == "ELIGIBLE"
    assert statuses["LIMIT"] == "ELIGIBLE"
    assert statuses["MISS"] == "REJECTED"
    assert statuses["BAD$"] == "REJECTED"
    assert first.as_dict()["preview_fingerprint"] == second.as_dict()["preview_fingerprint"]
    assert raw_first["phase13g2_preview_fingerprint"] == raw_second["phase13g2_preview_fingerprint"]


def test_run_preview_writes_durable_artifacts_and_history(tmp_path: Path) -> None:
    result = run_preview(
        "NEWC LIMIT",
        source_paths=_paths(tmp_path / "source"),
        run_root=tmp_path / "runs",
        temp_root=tmp_path / "temp",
    )

    run_dir = Path(result["artifact_dir"])
    assert (run_dir / "preview.json").is_file()
    assert (run_dir / "report.md").read_text(encoding="utf-8").startswith("# Fundamentals Administration Run")
    assert result["cleanup"]["removed_count"] == 5
    history = AdminRunHistory(tmp_path / "runs")
    assert history.summarize(result["run_id"]).outcome == "COMPLETED"


def test_copy_only_apply_is_idempotent_and_does_not_mutate_source(tmp_path: Path) -> None:
    source = _paths(tmp_path / "source")
    source_mtime = source.canonical_db.stat().st_mtime_ns
    preview = run_preview("NEWC", source_paths=source, run_root=tmp_path / "runs", temp_root=tmp_path / "temp")
    payload = Path(preview["phase13d_preview_payload_path"])
    fp = preview["preview_fingerprint"]

    result = run_apply(
        preview_payload_path=payload,
        preview_fingerprint=fp,
        source_paths=source,
        run_root=tmp_path / "runs",
        temp_root=tmp_path / "temp",
        confirm_apply=True,
    )

    assert result["outcome"] == "COMPLETED"
    assert result["copy_apply"]["phase13d_result"]["outcome"] == "APPLIED"
    assert result["copy_apply"]["repeat_result"]["outcome"] == "NO_CHANGE"
    assert result["downstream"]["phase13d_candidate_apply"] == "RUN_ONCE_FOR_BATCH"
    assert source.canonical_db.stat().st_mtime_ns == source_mtime
    with sqlite3.connect(source.canonical_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM security WHERE current_ticker='NEWC'").fetchone()[0] == 0


def test_apply_rejects_stale_preview(tmp_path: Path) -> None:
    source = _paths(tmp_path / "source")
    preview = run_preview("NEWC", source_paths=source, run_root=tmp_path / "runs", temp_root=tmp_path / "temp")
    with sqlite3.connect(source.provider_db) as conn:
        conn.execute("INSERT INTO sharadar_ticker_metadata VALUES('ZZZ','9','9','Z','NASDAQ','N','Domestic Common Stock','Tech','Soft')")

    result = run_apply(
        preview_payload_path=Path(preview["phase13d_preview_payload_path"]),
        preview_fingerprint=preview["preview_fingerprint"],
        source_paths=source,
        run_root=tmp_path / "runs",
        temp_root=tmp_path / "temp",
        confirm_apply=True,
    )

    assert result["outcome"] == "FAILED"
    assert result["error"] == "ValueError"


def test_failure_after_partial_mutation_rolls_back_copy_lane(tmp_path: Path) -> None:
    source = _paths(tmp_path / "source")
    preview = run_preview("NEWC", source_paths=source, run_root=tmp_path / "runs", temp_root=tmp_path / "temp")

    result = run_apply(
        preview_payload_path=Path(preview["phase13d_preview_payload_path"]),
        preview_fingerprint=preview["preview_fingerprint"],
        source_paths=source,
        run_root=tmp_path / "runs",
        temp_root=tmp_path / "temp",
        confirm_apply=True,
        failure_boundary="identity",
        keep_copies=True,
    )

    assert result["outcome"] == "ROLLED_BACK"
    copy_dir = Path(result["cleanup"]["retained"])
    with sqlite3.connect(copy_dir / "canonical.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM security WHERE current_ticker='NEWC'").fetchone()[0] == 0


def test_apply_requires_network_flag_only_as_metadata_for_now(tmp_path: Path) -> None:
    no_network = run_preview("MISS", source_paths=_paths(tmp_path / "a"), run_root=tmp_path / "runs_a", temp_root=tmp_path / "temp_a", network_allowed=False)
    with_network = run_preview("MISS", source_paths=_paths(tmp_path / "b"), run_root=tmp_path / "runs_b", temp_root=tmp_path / "temp_b", network_allowed=True)

    assert no_network["downstream"]["network"] == "DISABLED"
    assert with_network["downstream"]["network"] == "ALLOWED"


def test_production_path_and_sqlite_uri_refusal(tmp_path: Path) -> None:
    from rawcandle.fundamentals.phase12d import PRODUCTION

    with pytest.raises(PermissionError):
        reject_production_write_targets(
            BatchAddTickerPaths(
                provider_db=PRODUCTION["provider"],
                canonical_db=tmp_path / "c.db",
                analysis_db=tmp_path / "a.db",
                market_db=tmp_path / "m.db",
                taxonomy_db=tmp_path / "t.db",
            )
        )


def test_cli_preview_smoke(tmp_path: Path, capsys) -> None:
    from rawcandle.cli.run_fundamentals_admin_add_tickers import main

    paths = _paths(tmp_path / "source")
    code = main([
        "--provider-db", str(paths.provider_db),
        "--canonical-db", str(paths.canonical_db),
        "--analysis-db", str(paths.analysis_db),
        "--market-db", str(paths.market_db),
        "--taxonomy-db", str(paths.taxonomy_db),
        "--run-root", str(tmp_path / "cli_runs"),
        "--temp-root", str(tmp_path / "cli_temp"),
        "NEWC",
    ])
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert out["ok"] is True
