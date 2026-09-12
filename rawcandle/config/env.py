from __future__ import annotations

import os
import re
from pathlib import Path
from typing import MutableMapping


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_PATH = REPO_ROOT / ".env"
_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _strip_inline_comment(value: str) -> str:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char in {"'", '"'}:
            quote = None if quote == char else char if quote is None else quote
            continue
        if char == "#" and quote is None and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
    return value.strip()


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        key, separator, raw_value = stripped.partition("=")
        key = key.strip()
        if separator != "=" or not _KEY_RE.match(key):
            continue
        value = _strip_inline_comment(raw_value.strip())
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def load_repo_env(
    *,
    env_file: Path = DEFAULT_ENV_PATH,
    environ: MutableMapping[str, str] | None = None,
    override: bool = False,
) -> dict[str, str]:
    target = environ if environ is not None else os.environ
    loaded: dict[str, str] = {}
    for key, value in parse_env_file(env_file).items():
        if override or key not in target:
            target[key] = value
            loaded[key] = value
    return loaded


def get_env(name: str, *, env_file: Path = DEFAULT_ENV_PATH) -> str | None:
    load_repo_env(env_file=env_file)
    return os.environ.get(name)


def require_env(name: str, *, env_file: Path = DEFAULT_ENV_PATH) -> str:
    value = get_env(name, env_file=env_file)
    if not value:
        raise RuntimeError(f"{name}_NOT_CONFIGURED; set it in {env_file}")
    return value
