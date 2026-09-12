from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals.phase13d_backend import (
    Phase13DPaths,
    apply_taxonomy_preview,
    apply_ticker_preview,
    build_taxonomy_preview,
    build_ticker_preview,
    parse_ticker_tokens,
    reject_production_or_alias,
    stage_mock_provider_response,
)
from rawcandle.fundamentals.phase12d import write_json
from tests.test_phase13b_foundation import _analysis, _canonical, _taxonomy


def _provider(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE sharadar_ticker_metadata(
                ticker TEXT, permaticker TEXT, cik TEXT, name TEXT,
                category TEXT, sector TEXT, industry TEXT
            );
            INSERT INTO sharadar_ticker_metadata VALUES
                ('NEWC','1001','101','New Co','Domestic Common Stock','Technology','Software'),
                ('BADF','1002','102','Bad Fund','ETF','Financials','Fund'),
                ('LIMIT','1003','103','Limited Taxonomy','Domestic Common Stock','Industrials','Tools');
            """
        )


def _market(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE osakedata(osake TEXT, market TEXT, pvm TEXT, close REAL);
            INSERT INTO osakedata VALUES
                ('NEWC','usa','2026-09-10',10.0),
                ('LIMIT','usa','2026-09-10',11.0),
                ('BADF','usa','2026-09-10',12.0),
                ('AMBIG','usa','2026-09-10',13.0),
                ('AMBIG','omxh','2026-09-10',14.0);
            """
        )


def _paths(tmp_path: Path) -> Phase13DPaths:
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
    return Phase13DPaths(provider, canonical, analysis, market, taxonomy)


def _write(path: Path, payload: object) -> Path:
    write_json(path, payload)
    return path


def test_parse_ticker_tokens_deduplicates_and_rejects_bad_symbols() -> None:
    parsed = parse_ticker_tokens(" newc,NEWC bad$ limit\nambig ")
    assert parsed["accepted"] == ["NEWC", "LIMIT", "AMBIG"]
    assert parsed["rejected"] == [{"ticker": "BAD$", "reason": "MALFORMED_SYMBOL"}]


def test_ticker_preview_is_read_only_and_classifies_evidence(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    before = paths.canonical_db.stat().st_mtime_ns

    preview = build_ticker_preview(paths, "AAA NEWC LIMIT MISS AMBIG BADF", now="2026-09-11T10:00:00Z")
    statuses = {row["ticker"]: row["status"] for row in preview["ticker_results"]}

    assert statuses == {
        "AAA": "ALREADY_PRESENT",
        "NEWC": "READY_WITH_LIMITATIONS",
        "LIMIT": "READY_WITH_LIMITATIONS",
        "MISS": "MARKET_DATA_NOT_FOUND",
        "AMBIG": "MARKET_AMBIGUOUS",
        "BADF": "UNSUPPORTED_SECURITY_TYPE",
    }
    assert preview["accepted_tickers"] == ["NEWC", "LIMIT"]
    assert paths.canonical_db.stat().st_mtime_ns == before


def test_ticker_apply_rebuilds_copy_dependencies_and_second_apply_no_changes(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    preview = build_ticker_preview(paths, "NEWC", now="2026-09-12T10:00:00Z")
    preview_path = _write(tmp_path / "preview.json", preview)

    dry = apply_ticker_preview(
        paths,
        preview_path=preview_path,
        preview_fingerprint=preview["preview_fingerprint"],
        apply=False,
    )
    assert dry["outcome"] == "DRY_RUN"

    result = apply_ticker_preview(
        paths,
        preview_path=preview_path,
        preview_fingerprint=preview["preview_fingerprint"],
        apply=True,
        confirm_apply=True,
        output=tmp_path / "out",
    )

    assert result["outcome"] == "APPLIED"
    assert result["inserted_companies"] == 1
    assert result["relative_valuation_state"] == "OPERATIONAL_UNIVERSE_MISMATCH"
    assert result["second_apply"]["outcome"] == "NO_CHANGE"
    assert result["second_physical_no_change"] is True
    with sqlite3.connect(paths.canonical_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM security WHERE current_ticker='NEWC'").fetchone()[0] == 1


def test_ticker_apply_failure_restores_all_copies(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    preview = build_ticker_preview(paths, "NEWC", now="2026-09-12T10:00:00Z")
    preview_path = _write(tmp_path / "preview.json", preview)

    with pytest.raises(RuntimeError, match="PHASE13D_INJECTED_AFTER_IDENTITY"):
        apply_ticker_preview(
            paths,
            preview_path=preview_path,
            preview_fingerprint=preview["preview_fingerprint"],
            apply=True,
            confirm_apply=True,
            output=tmp_path / "out",
            failure_boundary="identity",
        )

    with sqlite3.connect(paths.canonical_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM company WHERE company_key='PHASE13D_STAGED:NEWC'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM security WHERE current_ticker='NEWC'").fetchone()[0] == 0


def test_taxonomy_preview_and_apply_split_presentation_from_economic_changes(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    preview = build_taxonomy_preview(
        paths,
        [
            {"ticker": "AAA", "field": "entity_name", "current": "AAA", "proposed": "AAA Plc"},
            {"ticker": "AAA", "field": "peer_group", "current": "old", "proposed": "new"},
        ],
        now="2026-09-11T10:00:00Z",
    )

    assert [row["classification"] for row in preview["change_results"]] == [
        "PRESENTATION_ONLY_CHANGE",
        "PEER_GROUP_CHANGE",
    ]
    preview_path = _write(tmp_path / "taxonomy_preview.json", preview)
    result = apply_taxonomy_preview(
        paths,
        preview_path=preview_path,
        preview_fingerprint=preview["preview_fingerprint"],
        apply=True,
        confirm_apply=True,
        output=tmp_path / "taxonomy_out",
    )

    assert result["relative_valuation_state"] == "ECONOMIC_TAXONOMY_MISMATCH"
    with sqlite3.connect(paths.taxonomy_db) as conn:
        assert conn.execute("SELECT entity_name FROM ec_entity WHERE ticker='AAA'").fetchone()[0] == "AAA Plc"


def test_mock_provider_staging_never_performs_network_request(tmp_path: Path) -> None:
    response = tmp_path / "response.json"
    response.write_text(json.dumps({"records": [{"ticker": "NEWC", "name": "New Co"}]}), encoding="utf-8")

    result = stage_mock_provider_response("NEWC MISS", response_json=response, output=tmp_path / "stage.json")

    assert result["network_request_performed"] is False
    assert result["staged"][0]["status"] == "STAGED_MOCK_PROVIDER"
    assert result["missing"] == [{"ticker": "MISS", "status": "SHARADAR_NOT_FOUND"}]


def test_production_path_refusal_rejects_exact_protected_database() -> None:
    from rawcandle.fundamentals.phase12d import PRODUCTION

    paths = Phase13DPaths(
        provider_db=Path("/tmp/provider.db"),
        canonical_db=PRODUCTION["canonical"],
        analysis_db=Path("/tmp/analysis.db"),
        market_db=Path("/tmp/market.db"),
        taxonomy_db=Path("/tmp/taxonomy.db"),
    )
    with pytest.raises(PermissionError, match="PHASE13D_PRODUCTION_PATH_REFUSED"):
        reject_production_or_alias(paths)
