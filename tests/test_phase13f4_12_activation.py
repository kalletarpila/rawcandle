from __future__ import annotations

import json

from rawcandle.cli import run_phase13f4_12_structural_production as phase13f4_12


def test_phase13f4_12_pre_gate_accepts_required_commits_and_full_suite(monkeypatch, tmp_path) -> None:
    artifact = tmp_path / "suite"
    artifact.mkdir()
    (artifact / "exit_code").write_text("0\n", encoding="utf-8")
    (artifact / "summary.json").write_text(
        json.dumps({"exit_code": 0, "timed_out": False}),
        encoding="utf-8",
    )
    (artifact / "pytest.log").write_text(
        "2961 passed, 14 deselected, 8 warnings in 795.83s (0:13:15)\n",
        encoding="utf-8",
    )
    (artifact / "heartbeat.jsonl").write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(phase13f4_12, "FULL_SUITE_ARTIFACT", artifact)
    monkeypatch.setattr(phase13f4_12, "_git_commit_exists", lambda commit: True)

    gate = phase13f4_12.phase13f4_12_pre_gate()

    assert all(gate["required_commits"].values())
    assert gate["full_suite"]["exit_code"] == 0


def test_phase13f4_12_pre_gate_rejects_missing_commit(monkeypatch, tmp_path) -> None:
    artifact = tmp_path / "suite"
    artifact.mkdir()
    monkeypatch.setattr(phase13f4_12, "FULL_SUITE_ARTIFACT", artifact)
    monkeypatch.setattr(phase13f4_12, "_git_commit_exists", lambda commit: commit != "863af30")

    try:
        phase13f4_12.phase13f4_12_pre_gate()
    except RuntimeError as exc:
        assert "PHASE13F4_12_REQUIRED_COMMIT_MISSING" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("expected missing commit gate to fail")
