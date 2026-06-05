from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rawcandle.cli import write_v3_markdown_prototypes as cli


@dataclass(frozen=True)
class _Header:
    run_id: str
    ecosystem_code: str
    taxonomy_version_code: str
    signal_date: str
    window_code: str


@dataclass(frozen=True)
class _QueryData:
    report_header: _Header


def _fake_query_data(window_code: str) -> _QueryData:
    return _QueryData(
        report_header=_Header(
            run_id="run-1",
            ecosystem_code="DATACENTER",
            taxonomy_version_code="DC_TAXONOMY_FULL_V1",
            signal_date="2026-05-29",
            window_code=window_code,
        )
    )


def _install_stubs(monkeypatch, calls: list[tuple[str, str]]) -> None:
    for horizon in cli.VALID_HORIZONS:
        monkeypatch.setattr(
            cli,
            f"build_{horizon}_report_query_data",
            lambda db, run_id, horizon=horizon: calls.append(
                ("query", horizon)
            )
            or _fake_query_data(horizon),
        )
        monkeypatch.setattr(
            cli,
            f"render_{horizon}_markdown_report",
            lambda query_data, horizon=horizon: calls.append(("render", horizon))
            or f"# {horizon}\nrun={query_data.report_header.run_id}\n",
        )


def test_cli_writes_all_four_markdown_files_by_default(tmp_path, monkeypatch, capsys) -> None:
    calls: list[tuple[str, str]] = []
    _install_stubs(monkeypatch, calls)
    out_dir = tmp_path / "out"

    result = cli.main(
        ["--db", str(tmp_path / "analysis.db"), "--run-id", "run-1", "--out-dir", str(out_dir)]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert [path.name for path in sorted(out_dir.iterdir())] == [
        "datacenter_v3_daily_2026-05-29.md",
        "datacenter_v3_rolling2_2026-05-29.md",
        "datacenter_v3_rolling30_2026-05-29.md",
        "datacenter_v3_rolling5_2026-05-29.md",
    ]
    assert calls == [
        ("query", "rolling30"),
        ("render", "rolling30"),
        ("query", "rolling5"),
        ("render", "rolling5"),
        ("query", "rolling2"),
        ("render", "rolling2"),
        ("query", "daily"),
        ("render", "daily"),
    ]
    assert "horizons_written: rolling30, rolling5, rolling2, daily" in captured.out
    assert str(out_dir.resolve()) in captured.out


def test_cli_supports_only_single_horizon(tmp_path, monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    _install_stubs(monkeypatch, calls)
    out_dir = tmp_path / "out"

    result = cli.main(
        [
            "--db",
            str(tmp_path / "analysis.db"),
            "--run-id",
            "run-1",
            "--out-dir",
            str(out_dir),
            "--only",
            "rolling30",
        ]
    )

    assert result == 0
    assert [path.name for path in out_dir.iterdir()] == ["datacenter_v3_rolling30_2026-05-29.md"]
    assert calls == [("query", "rolling30"), ("render", "rolling30")]


def test_cli_supports_multiple_horizons_via_only(tmp_path, monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    _install_stubs(monkeypatch, calls)
    out_dir = tmp_path / "out"

    result = cli.main(
        [
            "--db",
            str(tmp_path / "analysis.db"),
            "--run-id",
            "run-1",
            "--out-dir",
            str(out_dir),
            "--only",
            "rolling30,daily",
        ]
    )

    assert result == 0
    assert [path.name for path in sorted(out_dir.iterdir())] == [
        "datacenter_v3_daily_2026-05-29.md",
        "datacenter_v3_rolling30_2026-05-29.md",
    ]
    assert calls == [
        ("query", "rolling30"),
        ("render", "rolling30"),
        ("query", "daily"),
        ("render", "daily"),
    ]


def test_cli_refuses_to_overwrite_without_flag(tmp_path, monkeypatch, capsys) -> None:
    calls: list[tuple[str, str]] = []
    _install_stubs(monkeypatch, calls)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    target = out_dir / "datacenter_v3_rolling30_2026-05-29.md"
    target.write_text("existing\n", encoding="utf-8")

    result = cli.main(
        [
            "--db",
            str(tmp_path / "analysis.db"),
            "--run-id",
            "run-1",
            "--out-dir",
            str(out_dir),
            "--only",
            "rolling30",
        ]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert "refusing to overwrite existing file without --overwrite" in captured.err
    assert target.read_text(encoding="utf-8") == "existing\n"


def test_cli_overwrites_when_flag_is_provided(tmp_path, monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    _install_stubs(monkeypatch, calls)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    target = out_dir / "datacenter_v3_rolling30_2026-05-29.md"
    target.write_text("existing\n", encoding="utf-8")

    result = cli.main(
        [
            "--db",
            str(tmp_path / "analysis.db"),
            "--run-id",
            "run-1",
            "--out-dir",
            str(out_dir),
            "--only",
            "rolling30",
            "--overwrite",
        ]
    )

    assert result == 0
    assert target.read_text(encoding="utf-8") == "# rolling30\nrun=run-1\n"


def test_cli_prints_output_paths(tmp_path, monkeypatch, capsys) -> None:
    calls: list[tuple[str, str]] = []
    _install_stubs(monkeypatch, calls)
    out_dir = tmp_path / "out"

    result = cli.main(
        [
            "--db",
            str(tmp_path / "analysis.db"),
            "--run-id",
            "run-1",
            "--out-dir",
            str(out_dir),
            "--only",
            "rolling30,daily",
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert str((out_dir / "datacenter_v3_rolling30_2026-05-29.md").resolve()) in captured.out
    assert str((out_dir / "datacenter_v3_daily_2026-05-29.md").resolve()) in captured.out
    assert "bytes=" in captured.out
    assert "lines=" in captured.out


def test_cli_returns_non_zero_for_unknown_horizon(tmp_path, monkeypatch, capsys) -> None:
    calls: list[tuple[str, str]] = []
    _install_stubs(monkeypatch, calls)

    result = cli.main(
        [
            "--db",
            str(tmp_path / "analysis.db"),
            "--run-id",
            "run-1",
            "--out-dir",
            str(tmp_path / "out"),
            "--only",
            "rolling30,weekly",
        ]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert "unknown horizon(s): weekly" in captured.err
    assert calls == []


def test_cli_does_not_write_outside_provided_output_directory(tmp_path, monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    _install_stubs(monkeypatch, calls)
    out_dir = tmp_path / "nested" / "out"

    result = cli.main(
        [
            "--db",
            str(tmp_path / "analysis.db"),
            "--run-id",
            "run-1",
            "--out-dir",
            str(out_dir),
            "--only",
            "rolling30",
        ]
    )

    assert result == 0
    assert [path.name for path in out_dir.iterdir()] == ["datacenter_v3_rolling30_2026-05-29.md"]
    assert list(tmp_path.glob("*.md")) == []


def test_cli_uses_v3_query_and_render_functions(tmp_path, monkeypatch) -> None:
    used: list[str] = []
    monkeypatch.setattr(
        cli,
        "build_rolling30_report_query_data",
        lambda db, run_id: used.append("v3-query") or _fake_query_data("rolling30"),
    )
    monkeypatch.setattr(
        cli,
        "render_rolling30_markdown_report",
        lambda query_data: used.append("v3-render") or "# rolling30\n",
    )
    monkeypatch.setattr(
        cli,
        "_horizon_specs",
        lambda: {
            "rolling30": (
                cli.build_rolling30_report_query_data,
                cli.render_rolling30_markdown_report,
            )
        },
    )

    result = cli.main(
        [
            "--db",
            str(tmp_path / "analysis.db"),
            "--run-id",
            "run-1",
            "--out-dir",
            str(tmp_path / "out"),
            "--only",
            "rolling30",
        ]
    )

    assert result == 0
    assert used == ["v3-query", "v3-render"]


def test_cli_uses_deterministic_filenames(tmp_path, monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    _install_stubs(monkeypatch, calls)
    out_dir = tmp_path / "out"

    result = cli.main(
        [
            "--db",
            str(tmp_path / "analysis.db"),
            "--run-id",
            "run-1",
            "--out-dir",
            str(out_dir),
            "--only",
            "daily",
        ]
    )

    assert result == 0
    assert (out_dir / "datacenter_v3_daily_2026-05-29.md").exists()
