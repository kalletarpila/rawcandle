from __future__ import annotations

from datetime import date
from pathlib import Path
import sqlite3

import pytest

from rawcandle.fundamentals.admin import taxonomy as admin_taxonomy
from rawcandle.fundamentals.phase12d import stable_hash
from rawcandle.fundamentals.operating_income_v2 import rehearsal, score, taxonomy_source
from rawcandle.fundamentals.score import engine as legacy_score


def _canonical_security_fixture(path: Path, tickers: list[tuple[int, str]]) -> Path:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE security(company_id INTEGER,current_ticker TEXT,active INTEGER)")
        connection.executemany("INSERT INTO security VALUES(?,?,1)", tickers)
    return path


def test_score_v2_does_not_call_legacy_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("legacy score engine called")

    monkeypatch.setattr(legacy_score, "compute_score_rows", forbidden)
    monkeypatch.setattr(legacy_score, "trajectory_points", forbidden)
    row = {
        "ttm_id": 1, "company_id": 1, "security_id": 1, "ticker": "AAA",
        "endpoint_quarter_id": 1, "endpoint_fiscal_year": 2026,
        "endpoint_fiscal_quarter": "Q1", "period_end": "2026-03-31",
        "ttm_source_available_date": "2026-04-15", "core_ttm_ready": 1,
        "ttm_revenue": 100.0, "ttm_operating_income": 10.0,
        "ttm_free_cashflow": 8.0, "cash": 20.0, "total_debt": 10.0,
        "shares_outstanding": 10.0,
    }
    result = score.compute_score_rows([row], {}, generated_at="test", run_id="test")
    assert len(result) == 1
    assert result[0]["model_fingerprint"] == score.MODEL_FINGERPRINT


def test_explicit_as_of_controls_freshness() -> None:
    row = {"company_id": 1, "ttm_id": 1, "ttm_source_available_date": "2026-09-07"}
    assert rehearsal._fresh([row], date(2026, 9, 6)) == []
    assert rehearsal._fresh([row], date(2026, 9, 7)) == [row]
    assert rehearsal._fresh([row], date(2027, 3, 7)) == []
    assert rehearsal.resolve_as_of("2026-09-18") == date(2026, 9, 18)


@pytest.mark.parametrize("role,eligible", [
    ("CORE", True), ("EXTENDED", True), ("WATCH_ONLY", False),
])
def test_dc_role_membership_uses_active_taxonomy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, role: str, eligible: bool,
) -> None:
    state = {
        "active_version": {"taxonomy_version_code": "DC_V1"},
        "semantic_fingerprint": "semantic-fp",
        "rows": [{
            "ticker": "AAA", "report_group_status": role, "entity_id": 42,
        }],
    }
    monkeypatch.setattr(admin_taxonomy, "_active_state", lambda *_: state)
    memberships, dependency = taxonomy_source.load_active_dc_memberships(
        Path("unused.db"), _canonical_security_fixture(tmp_path / "canonical.db", [(7, "AAA")]),
    )
    assert (memberships[7][0].role in {"CORE", "EXTENDED"}) is eligible
    assert dependency["domain"] == "dc_ecosystem"
    assert dependency["version"] == "DC_V1"
    assert dependency["semantic_fingerprint"] == "semantic-fp"


def test_dc_membership_removal_and_multiple_memberships(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    state = {
        "active_version": {"taxonomy_version_code": "DC_V2"},
        "semantic_fingerprint": "changed-fp",
        "rows": [
            {"ticker": "AAA", "report_group_status": "CORE", "entity_id": 1},
            {"ticker": "AAA", "report_group_status": "EXTENDED", "entity_id": 2},
            {"ticker": "BBB", "report_group_status": "WATCH_ONLY", "entity_id": 3},
        ],
    }
    monkeypatch.setattr(admin_taxonomy, "_active_state", lambda *_: state)
    memberships, dependency = taxonomy_source.load_active_dc_memberships(
        Path("unused.db"), _canonical_security_fixture(tmp_path / "canonical.db", [(1, "AAA"), (2, "BBB"), (3, "CCC")]),
    )
    assert [item.role for item in memberships[1]] == ["CORE", "EXTENDED"]
    assert memberships[2][0].role == "WATCH_ONLY"
    assert 3 not in memberships
    assert dependency["mapped_companies"] == 2


def test_dc_membership_resolves_second_active_security_of_same_company(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setattr(admin_taxonomy, "_active_state", lambda *_: {
        "active_version": {"taxonomy_version_code": "DC_V2"},
        "semantic_fingerprint": "semantic-fp",
        "rows": [{"ticker": "GOOGL", "report_group_status": "CORE", "entity_id": 9}],
    })
    canonical = _canonical_security_fixture(tmp_path / "canonical.db", [(969, "GOOG"), (969, "GOOGL")])
    memberships, _ = taxonomy_source.load_active_dc_memberships(Path("unused.db"), canonical)
    assert memberships[969][0].ecosystem_id == "DATACENTER"


def test_admin_semantic_fingerprint_is_stable_and_role_sensitive() -> None:
    row = {
        "taxonomy_version": "DC_V1", "ticker": "AAA", "layer": "Compute",
        "subindustry": "Processors", "report_group_status": "CORE", "is_primary": 1,
        "role_weight": 1.0, "notes": "",
    }
    def semantic_fingerprint(rows: list[dict[str, object]]) -> str:
        return stable_hash({
            "taxonomy_domain": "dc_ecosystem",
            "rows": admin_taxonomy._semantic_payload(rows),
        })

    first = semantic_fingerprint([row])
    assert first == semantic_fingerprint([dict(row)])
    assert first != semantic_fingerprint([{**row, "report_group_status": "WATCH_ONLY"}])
    assert first != semantic_fingerprint([{**row, "taxonomy_version": "DC_V2"}])
