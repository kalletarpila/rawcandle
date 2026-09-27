from pathlib import Path

import pytest

from rawcandle.cli import run_datacenter_weighting_v2_candidate_build as build_cli
from rawcandle.cli import run_datacenter_weighting_v2_ec_projection as projection_cli


def test_candidate_build_requires_exact_database_and_v2_confirmation(tmp_path) -> None:
    with pytest.raises(SystemExit):
        build_cli.main(
            [
                "--analysis-db", str(tmp_path / "candidate.db"),
                "--confirm-analysis-db", str(tmp_path / "other.db"),
                "--price-db", str(tmp_path / "prices.db"),
                "--taxonomy-csv", str(tmp_path / "taxonomy.csv"),
                "--taxonomy-version", "TAXONOMY",
                "--market", "usa",
                "--confirm-calc-version", "DC_SWING_OHLC_V2",
            ]
        )


def test_candidate_build_passes_explicit_v2_scope(monkeypatch, tmp_path) -> None:
    captured = {}
    monkeypatch.setattr(
        build_cli,
        "build_v2_candidate_generation",
        lambda **kwargs: captured.update(kwargs) or {"status": "OK"},
    )
    database = tmp_path / "candidate.db"
    result = build_cli.main(
        [
            "--analysis-db", str(database),
            "--confirm-analysis-db", str(database),
            "--price-db", str(tmp_path / "prices.db"),
            "--taxonomy-csv", str(tmp_path / "taxonomy.csv"),
            "--taxonomy-version", "TAXONOMY",
            "--market", "usa",
            "--confirm-calc-version", "DC_SWING_OHLC_V2",
        ]
    )
    assert result == 0
    assert captured["analysis_db"] == database
    assert captured["validated_chain_start_date"] == "2025-08-01"
    assert str(captured["created_at_utc"]).endswith("Z")


def test_ec_projection_requires_exact_target_and_v2_confirmation(tmp_path) -> None:
    with pytest.raises(SystemExit):
        projection_cli.main(
            [
                "--source-db", str(tmp_path / "source.db"),
                "--target-db", str(tmp_path / "target.db"),
                "--confirm-target-db", str(tmp_path / "other.db"),
                "--taxonomy-version", "TAXONOMY",
                "--start-date", "2025-08-01",
                "--end-date", "2026-09-25",
                "--confirm-calc-version", "DC_SWING_OHLC_V2",
            ]
        )


def test_ec_projection_passes_explicit_range(monkeypatch, tmp_path) -> None:
    captured = {}
    monkeypatch.setattr(
        projection_cli,
        "project_v2_to_ec_range",
        lambda **kwargs: captured.update(kwargs) or {"status": "OK"},
    )
    target = tmp_path / "target.db"
    result = projection_cli.main(
        [
            "--source-db", str(tmp_path / "source.db"),
            "--target-db", str(target),
            "--confirm-target-db", str(target),
            "--taxonomy-version", "TAXONOMY",
            "--start-date", "2025-08-01",
            "--end-date", "2026-09-25",
            "--confirm-calc-version", "DC_SWING_OHLC_V2",
        ]
    )
    assert result == 0
    assert captured["target_db"] == Path(target)
    assert captured["start_date"] == "2025-08-01"
    assert captured["end_date"] == "2026-09-25"
