from __future__ import annotations

from pathlib import Path

from rawcandle.fundamentals.phase13d2_complete import TICKERS, _diff_values, resolve_output
from rawcandle.fundamentals.phase13d1_real_source import SNDK_PERMATICKER, archive_rows_for_ticker, sndk_identity_evidence
from tests.test_phase13d1_real_source import _canonical, _market, _provider, _taxonomy


def test_phase13d2_batch_order_is_deterministic_and_deduplicated() -> None:
    assert tuple(dict.fromkeys(TICKERS)) == ("AREB", "SNDK")


def test_phase13d2_sndk_source_uses_verified_archive_without_sndk1_rows() -> None:
    rows = archive_rows_for_ticker("SNDK", limit=50)
    assert rows
    assert {row["ticker"] for row in rows} == {"SNDK"}
    assert "SNDK1" not in {row["ticker"] for row in rows}


def test_phase13d2_sndk_identity_keeps_predecessor_separate(tmp_path: Path) -> None:
    provider = tmp_path / "provider.db"
    market = tmp_path / "market.db"
    canonical = tmp_path / "canonical.db"
    taxonomy = tmp_path / "taxonomy.db"
    _provider(provider)
    _market(market)
    _canonical(canonical)
    _taxonomy(taxonomy)

    evidence = sndk_identity_evidence(provider_db=provider, canonical_db=canonical, market_db=market, taxonomy_db=taxonomy)

    assert evidence["permanent_provider_identity"]["permaticker"] == SNDK_PERMATICKER
    assert any(row["ticker"] == "SNDK1" and row["permaticker"] == "197210" for row in evidence["predecessor_or_reuse_metadata"])


def test_phase13d2_resolves_relative_output_path_for_snapshot_sources(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    output = resolve_output(Path("relative-phase13d2-output"))

    assert output.is_absolute()
    assert output.name == "relative-phase13d2-output"


def test_phase13d2_determinism_diff_reports_field_paths() -> None:
    diffs = _diff_values(
        {"post": {"state": "COMPATIBLE", "snapshot_id": "one"}},
        {"post": {"state": "COMPATIBLE", "snapshot_id": "two"}},
    )

    assert diffs == [
        {
            "path": "$.post.snapshot_id",
            "left": "one",
            "right": "two",
            "kind": "value_mismatch",
        }
    ]
