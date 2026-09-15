from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace
from pathlib import Path
from zipfile import ZipFile

import pytest

from rawcandle.fundamentals.admin.batch_add_tickers import (
    BatchAddTickerPaths,
    build_generic_batch_plan,
    build_preview_from_copy,
    create_copy_lane,
    parse_batch_tickers,
    reject_production_write_targets,
    run_apply,
    run_preview,
)
from rawcandle.fundamentals.admin.history import AdminRunHistory
from rawcandle.fundamentals.phase12d import write_json
from rawcandle.fundamentals.schema.migrations import PROVIDER_SCHEMA_SQL
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


def _generic_paths(tmp_path: Path) -> BatchAddTickerPaths:
    tmp_path.mkdir(parents=True, exist_ok=True)
    provider = tmp_path / "provider.db"
    canonical = tmp_path / "canonical.db"
    analysis = tmp_path / "analysis.db"
    market = tmp_path / "market.db"
    taxonomy = tmp_path / "taxonomy.db"
    _canonical(canonical)
    _analysis(analysis)
    _market(market)
    _taxonomy(taxonomy)
    paths = BatchAddTickerPaths(provider, canonical, analysis, market, taxonomy)
    with sqlite3.connect(provider) as conn:
        conn.executescript(PROVIDER_SCHEMA_SQL)
        conn.execute(
            "INSERT INTO sharadar_ticker_metadata(table_name,ticker,permaticker,name,exchange,isdelisted,category,relatedtickers,secfilings,firstpricedate,lastpricedate,firstquarter,lastquarter,lastupdated,payload_json,fetched_at_utc) "
            "VALUES('fundamentals','NEWC','1001','New Co','NASDAQ','N','Domestic Common Stock','','https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000101','2020-01-01','2026-09-10','2020-03-31','2026-06-30','2026-09-10','{}','2026-09-10T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO sharadar_ticker_metadata(table_name,ticker,permaticker,name,exchange,isdelisted,category,relatedtickers,secfilings,firstpricedate,lastpricedate,firstquarter,lastquarter,lastupdated,payload_json,fetched_at_utc) "
            "VALUES('insiders','NEWC','1001','New Co','NASDAQ','N','Domestic Common Stock','','https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000101','2020-01-01','2026-09-10','2020-03-31','2026-06-30','2026-09-09','{}','2026-09-10T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO sharadar_ticker_metadata(table_name,ticker,permaticker,name,exchange,isdelisted,category,relatedtickers,secfilings,firstpricedate,lastpricedate,firstquarter,lastquarter,lastupdated,payload_json,fetched_at_utc) "
            "VALUES('fundamentals','ADR','2001','Adr Co','NYSE','N','ADR Common Stock','','https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000201','2020-01-01','2026-09-10','2020-03-31','2026-06-30','2026-09-10','{}','2026-09-10T00:00:00Z')"
        )
    with sqlite3.connect(paths.market_db) as conn:
        conn.execute("CREATE TABLE ticker_meta(ticker TEXT, market TEXT, sector TEXT, industry TEXT)")
        conn.execute("INSERT INTO ticker_meta VALUES('NEWC','usa','Technology','Software - Application')")
        conn.execute("INSERT INTO ticker_meta VALUES('ADR','usa','Technology','Semiconductors')")
        conn.execute("INSERT INTO osakedata VALUES('ADR','usa','2026-09-10',15.0)")
    return paths


def _archive(path: Path, tickers: tuple[str, ...] = ("NEWC",)) -> Path:
    fields = [
        "ticker", "dimension", "calendardate", "reportperiod", "fiscalperiod", "date", "lastupdated",
        "revenue", "gp", "opinc", "ebit", "ebitda", "netinc", "netinccmn", "ncfo", "capex", "fcf",
        "cashneq", "debt", "debtc", "debtnc", "sharesbas", "shareswa", "shareswadil",
        "receivables", "inventory", "payables", "deferredrev", "assets", "permaticker",
    ]
    lines = [",".join(fields)]
    for ticker in tickers:
        permaticker = "2001" if ticker == "ADR" else "1001"
        lines.append(",".join([
            ticker, "ARQ", "2026-06-30", "2026-06-30", "2026-Q2", "2026-08-01", "2026-08-01",
            "100", "60", "20", "20", "22", "10", "10", "15", "-5", "10", "50", "20", "5", "15",
            "1000", "1000", "1000", "10", "5", "4", "3", "200", permaticker,
        ]))
    with ZipFile(path, "w") as zf:
        zf.writestr("fundamentals-10Y.csv", "\n".join(lines) + "\n")
    return path


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
    assert result["downstream"]["authoritative_downstream"]["status"] == "NOT_AVAILABLE_FOR_GENERIC_BATCH_ADD_TICKERS"
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


def test_generic_plan_uses_fundamentals_metadata_and_verified_archive(tmp_path: Path) -> None:
    paths = _generic_paths(tmp_path / "source")
    request = parse_batch_tickers("NEWC")
    plan = build_generic_batch_plan(paths, request, now="2026-09-15T00:00:00Z", archive_path=_archive(tmp_path / "source.zip"))

    payload = plan.safe_dict(include_rows=True)
    item = payload["items"][0]
    assert item["status"] == "ELIGIBLE"
    assert item["source_category"] == "verified_archive"
    assert item["provider_metadata"]["identity"]["table_name"] == "fundamentals"
    assert item["provider_arq_row_count"] == 1
    assert payload["accepted_tickers"] == ["NEWC"]


def test_generic_plan_network_requires_flag_and_redacts_url(tmp_path: Path) -> None:
    paths = _generic_paths(tmp_path / "source")
    request = parse_batch_tickers("NEWC")
    disabled = build_generic_batch_plan(
        paths,
        request,
        now="2026-09-15T00:00:00Z",
        archive_path=tmp_path / "missing.zip",
        network_allowed=False,
    )
    assert disabled.items[0].status == "REVIEW_REQUIRED"
    assert disabled.items[0].source_category == "network_required"

    class FakeClient:
        request_count = 0

        def fundamentals(self, **kwargs):
            self.request_count += 1
            return SimpleNamespace(
                ok=True,
                status="SUCCESS",
                auth_status="AUTH_OK",
                http_status=200,
                endpoint="/data/fundamentals",
                url="https://api.example.test/data/fundamentals?ticker=NEWC&api_key=SECRET",
                request_count=self.request_count,
                records=[dict(_archive_row("NEWC"))],
            )

    enabled = build_generic_batch_plan(
        paths,
        request,
        now="2026-09-15T00:00:00Z",
        archive_path=tmp_path / "missing.zip",
        network_allowed=True,
        network_client=FakeClient(),
    ).safe_dict(include_rows=True)

    assert enabled["items"][0]["status"] == "ELIGIBLE"
    assert enabled["network"]["request_count"] == 1
    assert "SECRET" not in json.dumps(enabled["network"])
    assert "api_key=%2A%2A%2A" in enabled["network"]["calls"][0]["url"]


def _archive_row(ticker: str) -> dict[str, str]:
    return {
        "ticker": ticker,
        "dimension": "ARQ",
        "calendardate": "2026-06-30",
        "reportperiod": "2026-06-30",
        "fiscalperiod": "2026-Q2",
        "date": "2026-08-01",
        "lastupdated": "2026-08-01",
        "revenue": "100",
        "gp": "60",
        "opinc": "20",
        "ebit": "20",
        "ebitda": "22",
        "netinc": "10",
        "netinccmn": "10",
        "ncfo": "15",
        "capex": "-5",
        "fcf": "10",
        "cashneq": "50",
        "debt": "20",
        "debtc": "5",
        "debtnc": "15",
        "sharesbas": "1000",
        "shareswa": "1000",
        "shareswadil": "1000",
        "receivables": "10",
        "inventory": "5",
        "payables": "4",
        "deferredrev": "3",
        "assets": "200",
        "permaticker": "1001",
    }


def test_generic_apply_stages_all_items_before_one_downstream_batch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = _generic_paths(tmp_path / "source")
    archive = _archive(tmp_path / "source.zip", ("NEWC", "ADR"))
    monkeypatch.setattr("rawcandle.fundamentals.admin.batch_add_tickers.DEFAULT_ARCHIVE", archive)
    calls: list[dict[str, object]] = []

    def fake_downstream(copy_paths: BatchAddTickerPaths, output: Path, *, accepted_tickers, applied_at: str):
        with sqlite3.connect(copy_paths.canonical_db) as canonical, sqlite3.connect(copy_paths.provider_db) as provider:
            staged_tickers = {
                row[0]
                for row in provider.execute("SELECT DISTINCT provider_ticker FROM provider_observation")
            }
            security_tickers = {
                row[0]
                for row in canonical.execute("SELECT current_ticker FROM security WHERE current_ticker IN ('NEWC','ADR')")
            }
        calls.append({"accepted": tuple(accepted_tickers), "staged": staged_tickers, "securities": security_tickers})
        return {
            "package": {"first_apply": {"outcome": "APPLIED"}},
            "relative_position": {"apply": {"outcome": "APPLIED"}},
            "relative_valuation": {"first_apply": {"outcome": "ACTIVATED"}},
            "invocation_counts": {"package": 1, "relative_position": 1, "relative_valuation": 1},
        }

    monkeypatch.setattr("rawcandle.fundamentals.admin.batch_add_tickers._run_authoritative_downstream", fake_downstream)
    preview = run_preview("NEWC ADR", source_paths=paths, run_root=tmp_path / "runs", temp_root=tmp_path / "temp")
    result = run_apply(
        preview_payload_path=Path(preview["phase13d_preview_payload_path"]),
        preview_fingerprint=preview["preview_fingerprint"],
        source_paths=paths,
        run_root=tmp_path / "runs",
        temp_root=tmp_path / "temp",
        confirm_apply=True,
    )

    assert result["outcome"] == "COMPLETED"
    assert result["downstream"]["mode"] == "GENERIC_AUTHORITATIVE_BATCH"
    assert result["downstream"]["invocation_counts"] == {"package": 1, "relative_position": 1, "relative_valuation": 1}
    assert calls == [{"accepted": ("NEWC", "ADR"), "staged": {"NEWC", "ADR"}, "securities": {"NEWC", "ADR"}}]


def test_generic_apply_rolls_back_after_identity_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = _generic_paths(tmp_path / "source")
    monkeypatch.setattr("rawcandle.fundamentals.admin.batch_add_tickers.DEFAULT_ARCHIVE", _archive(tmp_path / "source.zip"))
    preview = run_preview("NEWC", source_paths=paths, run_root=tmp_path / "runs", temp_root=tmp_path / "temp")

    result = run_apply(
        preview_payload_path=Path(preview["phase13d_preview_payload_path"]),
        preview_fingerprint=preview["preview_fingerprint"],
        source_paths=paths,
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
