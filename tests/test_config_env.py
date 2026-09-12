from __future__ import annotations

from pathlib import Path

from rawcandle.config.env import load_repo_env, parse_env_file, require_env


def test_parse_env_file_supports_export_quotes_and_comments(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        """
        # local secrets
        export SHARADAR_API_KEY="secret value" # keep this private
        EMPTY=
        POLYGON_API_KEY='polygon-key'
        BAD-NAME=ignored
        """,
        encoding="utf-8",
    )

    assert parse_env_file(env_file) == {
        "SHARADAR_API_KEY": "secret value",
        "EMPTY": "",
        "POLYGON_API_KEY": "polygon-key",
    }


def test_load_repo_env_does_not_override_existing_values(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SHARADAR_API_KEY=file-key\nOTHER=value\n", encoding="utf-8")
    environ = {"SHARADAR_API_KEY": "process-key"}

    loaded = load_repo_env(env_file=env_file, environ=environ)

    assert loaded == {"OTHER": "value"}
    assert environ["SHARADAR_API_KEY"] == "process-key"
    assert environ["OTHER"] == "value"


def test_require_env_loads_from_explicit_file(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SHARADAR_API_KEY=file-key\n", encoding="utf-8")
    monkeypatch.delenv("SHARADAR_API_KEY", raising=False)

    assert require_env("SHARADAR_API_KEY", env_file=env_file) == "file-key"
