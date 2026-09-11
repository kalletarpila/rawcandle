from __future__ import annotations

import copy
import sqlite3
from argparse import Namespace
from pathlib import Path

import pytest

from rawcandle.cli.run_fundamentals_v4_relative_valuation_production import build_parser
from rawcandle.fundamentals.relative_valuation import production
from rawcandle.fundamentals.relative_valuation.candidate_snapshot import (
    PRODUCTION_REPORT_PRESENTATION_FINGERPRINT,
    PRODUCTION_SNAPSHOT_FINGERPRINT,
    PRODUCTION_SNAPSHOT_MODEL_VERSION,
    attach_relative_valuation_unavailable,
)
from rawcandle.fundamentals.relative_valuation.contract import PRODUCTION_REPORT_CONTRACT
from rawcandle.fundamentals.relative_valuation.engine import MODEL_FINGERPRINT
from rawcandle.fundamentals.relative_valuation.persistence import (
    LAYOUT_FINGERPRINT, RelativeValuationRepository,
    PERSISTENCE_VERSION,
    deactivate_snapshot,
    ensure_schema,
    set_active_snapshot,
)
from rawcandle.fundamentals.snapshot.active import generate_active_company_snapshot
from rawcandle.fundamentals.snapshot.assembler import SnapshotPaths
from rawcandle.fundamentals.snapshot.renderer import render_snapshot
def _role_database(path: Path, table: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(f'CREATE TABLE "{table}" (value INTEGER)')


def _args(paths: dict[str, Path], output: Path, **changes: object) -> Namespace:
    values: dict[str, object] = {
        **{f"{name}_db": path for name, path in paths.items()},
        "output": output,
        "backup_dir": output.parent / "backups",
        "as_of_date": "2026-09-08",
        "model_fingerprint": MODEL_FINGERPRINT,
        "persistence_version": PERSISTENCE_VERSION,
        "layout_fingerprint": LAYOUT_FINGERPRINT,
        "expected_active_package": production.LOCKED_PACKAGE,
        "expected_source_fingerprint": "s" * 64,
        "expected_result_fingerprint": "r" * 64,
        "expected_physical_fingerprint": "p" * 64,
        "expected_snapshot_id": "i" * 64,
        "full_universe": True,
        "apply": False,
        "confirm_production": False,
    }
    values.update(changes)
    return Namespace(**values)


def test_production_parser_defaults_to_dry_run() -> None:
    parser = build_parser()
    help_text = parser.format_help()
    assert "--confirm-production" in help_text
    assert "--full-universe" in help_text
    assert "--expected-physical-fingerprint" in help_text
    assert len(PRODUCTION_SNAPSHOT_FINGERPRINT) == 64
    assert len(PRODUCTION_REPORT_PRESENTATION_FINGERPRINT) == 64
    assert "CANDIDATE" not in PRODUCTION_REPORT_CONTRACT
    assert PRODUCTION_SNAPSHOT_MODEL_VERSION.endswith("RELATIVE_VALUATION_V2")
    assert PRODUCTION_SNAPSHOT_FINGERPRINT == "7b40558063684256474afa885e60e73d97f01fc01989ae9ffbcae34e74f4dd36"
    assert PRODUCTION_REPORT_CONTRACT == (
        "CURRENT_REVISED_COMPANY_SNAPSHOT_V2_PRESENTATION_V10_"
        "RELATIVE_VALUATION_FROZEN"
    )
    assert PRODUCTION_REPORT_PRESENTATION_FINGERPRINT == "d4e90e7ac75a5cfc76e87fa8855b9191485b3305193871396ca0776402fce9c0"
    required = {
        action.dest for action in parser._actions if action.required
    }
    assert {
        "canonical_db", "provider_db", "analysis_db", "market_db", "taxonomy_db"
    } <= required


def test_production_gate_requires_exact_roles_and_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = {name: tmp_path / f"{name}.db" for name in production.PRODUCTION_PATHS}
    for name, path in paths.items():
        _role_database(path, production.DATABASE_TYPES[name])
    output_root = tmp_path / "artifacts"
    backup_root = tmp_path / "backups"
    monkeypatch.setattr(production, "PRODUCTION_PATHS", paths)
    monkeypatch.setattr(production, "ARTIFACT_ROOT", output_root)
    monkeypatch.setattr(production, "BACKUP_DIR", backup_root)
    args = _args(paths, output_root / "run")
    args.backup_dir = backup_root
    assert production.validate_production_request(args)["analysis"] == str(paths["analysis"])
    with pytest.raises(PermissionError, match="CONFIRMATION"):
        production.validate_production_request(
            _args(paths, output_root / "apply", backup_dir=backup_root, apply=True)
        )
    wrong = _args(paths, output_root / "wrong", backup_dir=backup_root)
    wrong.layout_fingerprint = "wrong"
    with pytest.raises(ValueError, match="LAYOUT"):
        production.validate_production_request(wrong)
    unknown_package = _args(paths, output_root / "package", backup_dir=backup_root)
    unknown_package.expected_active_package = "unknown"
    with pytest.raises(ValueError, match="ACTIVE_PACKAGE"):
        production.validate_production_request(unknown_package)
    alias = tmp_path / "analysis-alias.db"
    alias.symlink_to(paths["analysis"])
    symlinked = _args(paths, output_root / "alias", backup_dir=backup_root)
    symlinked.analysis_db = alias
    with pytest.raises(PermissionError, match="ANALYSIS"):
        production.validate_production_request(symlinked)


def test_activation_and_deactivation_are_explicit_and_transactional() -> None:
    connection = sqlite3.connect(":memory:")
    ensure_schema(connection, applied_at_utc="2026-09-08T00:00:00Z")
    connection.execute(
        "INSERT INTO relative_valuation_snapshot VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "snapshot", "version", MODEL_FINGERPRINT, PERSISTENCE_VERSION,
            LAYOUT_FINGERPRINT, "CURRENTLY_REVISED_NOT_PIT", "2026-09-08",
            "2026-09-08T00:00:00Z", "source", "result", "physical", None,
            None, "COMPLETE", 0, 0, 0, 0, 0, "2026-09-08T00:00:00Z",
            "2026-09-08T00:00:00Z",
        ),
    )
    set_active_snapshot(
        connection, model_fingerprint=MODEL_FINGERPRINT,
        snapshot_id="snapshot", activated_at_utc="2026-09-08T00:01:00Z",
    )
    assert connection.execute("SELECT snapshot_id FROM relative_valuation_active_snapshot").fetchone()[0] == "snapshot"
    assert deactivate_snapshot(connection, model_fingerprint=MODEL_FINGERPRINT) == 1
    assert connection.execute("SELECT COUNT(*) FROM relative_valuation_active_snapshot").fetchone()[0] == 0


def test_unavailable_report_is_explicit_and_uses_production_identities() -> None:
    base = {
        "identity": {"ticker": "TEST"},
        "report_date": "2026-09-07",
        "model_fingerprints": {"snapshot": "base"},
        "report_contract": "CURRENT_REVISED_COMPANY_SNAPSHOT_V2_PRESENTATION_V7",
        "report_presentation_fingerprint": "base",
    }
    snapshot = attach_relative_valuation_unavailable(
        base,
        reason_code="RELATIVE_VALUATION_NO_ELIGIBLE_NON_FUTURE_SNAPSHOT",
        metadata={"as_of_date": "2026-09-08"},
    )
    assert snapshot["report_contract"] == PRODUCTION_REPORT_CONTRACT
    assert snapshot["report_presentation_fingerprint"] == PRODUCTION_REPORT_PRESENTATION_FINGERPRINT
    assert snapshot["model_fingerprints"]["snapshot"] == PRODUCTION_SNAPSHOT_FINGERPRINT
    markdown = "\n".join(__import__(
        "rawcandle.fundamentals.snapshot.renderer", fromlist=["_relative_valuation_sections"]
    )._relative_valuation_sections(snapshot))
    assert "RELATIVE_VALUATION_NO_ELIGIBLE_NON_FUTURE_SNAPSHOT" in markdown
    assert "2026-09-08" in markdown and "uudelleenlaskentaa" in markdown

    missing = attach_relative_valuation_unavailable(
        base,
        reason_code="RELATIVE_VALUATION_COMPANY_NOT_IN_SNAPSHOT",
        metadata={"as_of_date": "2026-09-08"},
    )
    missing_markdown = "\n".join(__import__(
        "rawcandle.fundamentals.snapshot.renderer",
        fromlist=["_relative_valuation_sections"],
    )._relative_valuation_sections(missing))
    assert "RELATIVE_VALUATION_COMPANY_NOT_IN_SNAPSHOT" in missing_markdown
    assert "kelvollinen snapshot: `2026-09-08`" in missing_markdown


@pytest.mark.integration
@pytest.mark.database
def test_future_report_uses_active_snapshot_without_refresh_or_database_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).resolve().parents[1]
    paths = SnapshotPaths(
        canonical_db=root / "data/fundamentals_v4.db",
        analysis_db=root / "data/fundamentals_analysis.db",
        market_db=root / "data/osakedata.db",
        taxonomy_db=root / "data/analysis.db",
        provider_db=root / "data/fundamentals_provider.db",
    )
    if not all(path.is_file() for path in paths.__dict__.values()):
        pytest.skip("Fundamentals V4 production databases are not present")
    before = {
        name: (path.stat().st_size, path.stat().st_mtime_ns)
        for name, path in paths.__dict__.items()
    }
    import rawcandle.fundamentals.relative_valuation.engine as engine_module
    import rawcandle.fundamentals.relative_valuation.persistence as persistence_module

    def forbidden(*args, **kwargs):
        raise AssertionError("REPORT_GENERATION_MUST_NOT_REFRESH_RELATIVE_VALUATION")

    monkeypatch.setattr(engine_module, "calculate_relative_valuation", forbidden)
    monkeypatch.setattr(persistence_module, "apply_snapshot", forbidden)
    first = generate_active_company_snapshot(
        paths, ticker="NVDA", report_date="2026-09-09", output_dir=tmp_path
    )
    second = generate_active_company_snapshot(
        paths, ticker="NVDA", report_date="2026-09-09", output_dir=tmp_path
    )
    markdown = Path(first["output_path"]).read_text(encoding="utf-8")
    relative = first["snapshot"]["relative_valuation"]
    identity = first["snapshot"]["relative_valuation_identity"]
    with sqlite3.connect(
        f"{paths.analysis_db.resolve().as_uri()}?mode=ro", uri=True
    ) as connection:
        persisted = RelativeValuationRepository(connection).company_by_ticker(
            "NVDA", model_fingerprint=MODEL_FINGERPRINT
        )
    with sqlite3.connect(
        f"{paths.market_db.resolve().as_uri()}?mode=ro", uri=True
    ) as connection:
        expected_current_price_date = connection.execute(
            "SELECT MAX(pvm) FROM osakedata WHERE osake=? AND market=? AND pvm<=?",
            ("NVDA", "usa", "2026-09-09"),
        ).fetchone()[0]

    assert first["status"] == "CREATED" and second["status"] == "NO_CHANGE"
    assert first["report_content_fingerprint"] == second["report_content_fingerprint"]
    assert identity["as_of_date"] == "2026-09-08"
    assert relative["current_valuation"]["price_date"] == "2026-09-04"
    assert first["snapshot"]["current_price_valuation"]["price_date"] == expected_current_price_date
    for expected in (
        "Report date: `2026-09-09`",
        "Relative Valuation snapshot date: `2026-09-08`",
        "snapshotissa `2026-09-08` yhtiön `2026-09-04` päivän hinnalla",
        f"Indicative current-price valuation käyttää `{expected_current_price_date}` päivän hintaa",
        "Persisted peer comparison — snapshot 2026-09-08",
        "Snapshot-price Absolute Valuation Score",
        "Snapshot-hintainen",
        "ei lasketa uutta persentiiliä raportin nykyhinnalla",
        "| Snapshot-price Absolute Valuation Score | 27.02 | 24.15 | −2.87 p |",
    ):
        assert expected in markdown
    assert "Current-price peer comparison" not in markdown
    assert "Nykyhintapersentiiliä ei lasketa eikä esitetä." not in markdown
    assert "peer-snapshotin uudelleenrakennusta" in markdown
    assert "Smallest component history count" in markdown
    assert "40% × Operating Income / EV" in markdown
    assert "40% × FCF / Market Cap" in markdown
    assert "20% × Reported Common Earnings / Market Cap" in markdown
    assert "READY vaatii vähintään 12" in markdown
    assert "LIMITED_HISTORY vaatii vähintään 8" in markdown
    assert "percentage discount" in markdown
    assert "probability of price appreciation" in markdown
    assert "company_id" not in markdown and "snapshot_id" not in markdown

    distinct_dates = copy.deepcopy(first["snapshot"])
    distinct_dates["report_date"] = "2026-09-10"
    distinct_dates["current_price_valuation"]["price_date"] = "2026-09-09"
    distinct_markdown = render_snapshot(distinct_dates).markdown
    assert len({
        distinct_dates["report_date"],
        distinct_dates["relative_valuation_identity"]["as_of_date"],
        distinct_dates["relative_valuation"]["current_valuation"]["price_date"],
        distinct_dates["current_price_valuation"]["price_date"],
    }) == 4
    for date_value in ("2026-09-10", "2026-09-08", "2026-09-04", "2026-09-09"):
        assert date_value in distinct_markdown
    assert (
        relative["current_valuation"]["total_valuation_score"]
        == persisted["current_valuation_score"]
    )
    assert (
        relative["current_valuation"]["price_date"]
        == persisted["current_price_date"]
    )
    after = {
        name: (path.stat().st_size, path.stat().st_mtime_ns)
        for name, path in paths.__dict__.items()
    }
    assert after == before
