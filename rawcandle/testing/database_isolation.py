from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import parse_qs, unquote, urlsplit


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

# These paths come from scheduler_config.json, the Fundamentals production
# manifests/runbooks, and the two repository production-tool defaults.
PROTECTED_DATABASE_ROLES: Mapping[str, Path] = {
    "analysis_classification": REPOSITORY_ROOT / "data" / "analysis.db",
    "market_data": REPOSITORY_ROOT / "data" / "osakedata.db",
    "fundamentals_provider": REPOSITORY_ROOT / "data" / "fundamentals_provider.db",
    "fundamentals_canonical": REPOSITORY_ROOT / "data" / "fundamentals_v4.db",
    "fundamentals_analysis": REPOSITORY_ROOT / "data" / "fundamentals_analysis.db",
    "combo_edge_workbench": REPOSITORY_ROOT / "data" / "combo_edge_workbench.db",
    "ecosystem_dashboard": REPOSITORY_ROOT / "data" / "ecosystem_dashboard.db",
}

PROTECTED_DATABASE_PATHS = frozenset(
    path.resolve(strict=False) for path in PROTECTED_DATABASE_ROLES.values()
)

_ORIGINAL_CONNECT = sqlite3.dbapi2.connect
_GUARD_INSTALLED = False

_ATTACH_RE = re.compile(
    r"^\s*ATTACH\s+(?:DATABASE\s+)?(?P<target>\?|:[A-Za-z_]\w*|'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\")",
    re.IGNORECASE,
)
_VACUUM_INTO_RE = re.compile(
    r"^\s*VACUUM(?:\s+[A-Za-z_]\w*)?\s+INTO\s+(?P<target>\?|:[A-Za-z_]\w*|'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\")",
    re.IGNORECASE,
)


class ProtectedDatabaseWriteError(PermissionError):
    """Raised before a test can open a production database as writable."""


@dataclass(frozen=True)
class FileState:
    path: str
    exists: bool
    size: int | None
    mtime_ns: int | None
    sha256: str | None


def _database_path_and_mode(
    database: str | bytes | os.PathLike[str] | os.PathLike[bytes],
    *,
    uri: bool,
) -> tuple[Path | None, str | None]:
    raw = os.fsdecode(database)
    if raw == ":memory:":
        return None, None

    mode = None
    if uri or raw.startswith("file:"):
        split = urlsplit(raw)
        if split.scheme != "file":
            return None, None
        query = parse_qs(split.query, keep_blank_values=True)
        mode = query.get("mode", [None])[-1]
        if split.netloc and split.netloc not in ("", "localhost"):
            raw_path = f"//{split.netloc}{unquote(split.path)}"
        else:
            raw_path = unquote(split.path)
    else:
        raw_path = raw

    if raw_path in ("", ":memory:") or mode == "memory":
        return None, mode
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve(strict=False), mode


def resolve_database_path(
    database: str | bytes | os.PathLike[str] | os.PathLike[bytes],
    *,
    uri: bool = False,
) -> Path | None:
    """Resolve plain, relative, symlinked, and SQLite URI database targets."""

    return _database_path_and_mode(database, uri=uri)[0]


def assert_test_database_access(
    database: str | bytes | os.PathLike[str] | os.PathLike[bytes],
    *,
    uri: bool = False,
) -> None:
    """Reject writable SQLite opens of protected production databases."""

    path, mode = _database_path_and_mode(database, uri=uri)
    if path not in PROTECTED_DATABASE_PATHS:
        return
    if uri and mode == "ro":
        return
    raise ProtectedDatabaseWriteError(
        f"TEST_PRODUCTION_DATABASE_WRITE_REJECTED:{path}; "
        "use tmp_path or an explicit SQLite mode=ro URI"
    )


def require_test_database_path(
    database: str | bytes | os.PathLike[str] | os.PathLike[bytes] | None,
    *,
    setting: str,
) -> Path:
    """Validate an explicitly supplied writable test destination."""

    if database is None or not os.fsdecode(database).strip():
        raise ValueError(f"MISSING_TEST_DATABASE_PATH:{setting}")
    assert_test_database_access(database)
    resolved = resolve_database_path(database)
    if resolved is None:
        raise ValueError(f"INVALID_TEST_DATABASE_PATH:{setting}")
    return resolved


def _bound_target(token: str, parameters: Any) -> str:
    if token == "?":
        if not isinstance(parameters, (tuple, list)) or not parameters:
            raise ProtectedDatabaseWriteError("TEST_SQLITE_TARGET_UNRESOLVED")
        return os.fsdecode(parameters[0])
    if token.startswith(":"):
        if not isinstance(parameters, Mapping) or token[1:] not in parameters:
            raise ProtectedDatabaseWriteError("TEST_SQLITE_TARGET_UNRESOLVED")
        return os.fsdecode(parameters[token[1:]])
    quote = token[0]
    return token[1:-1].replace(quote * 2, quote)


def _guard_sql_statement(sql: str, parameters: Any = ()) -> None:
    for pattern in (_ATTACH_RE, _VACUUM_INTO_RE):
        match = pattern.match(sql)
        if match is None:
            continue
        target = _bound_target(match.group("target"), parameters)
        assert_test_database_access(target, uri=target.startswith("file:"))


class GuardedCursor(sqlite3.Cursor):
    def execute(self, sql: str, parameters: Any = (), /) -> GuardedCursor:
        _guard_sql_statement(sql, parameters)
        return super().execute(sql, parameters)

    def executemany(self, sql: str, seq_of_parameters: Any, /) -> GuardedCursor:
        if _ATTACH_RE.match(sql) or _VACUUM_INTO_RE.match(sql):
            raise ProtectedDatabaseWriteError("TEST_SQLITE_MULTI_TARGET_OPERATION_REJECTED")
        return super().executemany(sql, seq_of_parameters)

    def executescript(self, sql_script: str, /) -> GuardedCursor:
        for statement in sql_script.split(";"):
            _guard_sql_statement(statement)
        return super().executescript(sql_script)


class GuardedConnection(sqlite3.Connection):
    def cursor(self, factory: Any = GuardedCursor) -> sqlite3.Cursor:
        return super().cursor(factory)

    def execute(self, sql: str, parameters: Any = (), /) -> sqlite3.Cursor:
        _guard_sql_statement(sql, parameters)
        return super().execute(sql, parameters)

    def executemany(self, sql: str, seq_of_parameters: Any, /) -> sqlite3.Cursor:
        if _ATTACH_RE.match(sql) or _VACUUM_INTO_RE.match(sql):
            raise ProtectedDatabaseWriteError("TEST_SQLITE_MULTI_TARGET_OPERATION_REJECTED")
        return super().executemany(sql, seq_of_parameters)

    def executescript(self, sql_script: str, /) -> sqlite3.Cursor:
        for statement in sql_script.split(";"):
            _guard_sql_statement(statement)
        return super().executescript(sql_script)


def guarded_sqlite_connect(database: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
    assert_test_database_access(database, uri=bool(kwargs.get("uri", False)))
    if "factory" in kwargs and kwargs["factory"] is not GuardedConnection:
        raise ProtectedDatabaseWriteError("TEST_CUSTOM_SQLITE_CONNECTION_FACTORY_REJECTED")
    kwargs["factory"] = GuardedConnection
    connection = _ORIGINAL_CONNECT(database, *args, **kwargs)

    def authorize(
        action: int,
        argument_one: str | None,
        _argument_two: str | None,
        _database_name: str | None,
        _trigger_name: str | None,
    ) -> int:
        if action != sqlite3.SQLITE_ATTACH or argument_one is None:
            return sqlite3.SQLITE_OK
        try:
            assert_test_database_access(argument_one, uri=argument_one.startswith("file:"))
        except ProtectedDatabaseWriteError:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    connection.set_authorizer(authorize)
    return connection


def install_sqlite_guard() -> None:
    """Install the process-local guard used by pytest and Python subprocesses."""

    global _GUARD_INSTALLED
    if _GUARD_INSTALLED:
        return
    sqlite3.connect = guarded_sqlite_connect
    sqlite3.dbapi2.connect = guarded_sqlite_connect
    _GUARD_INSTALLED = True


def connect_readonly(path: str | os.PathLike[str]) -> sqlite3.Connection:
    resolved = Path(path).resolve(strict=True)
    uri = f"{resolved.as_uri()}?mode=ro"
    return guarded_sqlite_connect(uri, uri=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def capture_file_state(path: Path, *, hash_content: bool = True) -> FileState:
    if not path.exists():
        return FileState(str(path), False, None, None, None)
    stat = path.stat()
    return FileState(
        path=str(path),
        exists=True,
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        sha256=_sha256(path) if hash_content else None,
    )


def capture_protected_file_inventory(*, hash_content: bool = True) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    for role, path in PROTECTED_DATABASE_ROLES.items():
        resolved = path.resolve(strict=False)
        inventory[role] = {
            "main": asdict(capture_file_state(resolved, hash_content=hash_content)),
            "wal": asdict(capture_file_state(Path(f"{resolved}-wal"), hash_content=hash_content)),
            "shm": asdict(capture_file_state(Path(f"{resolved}-shm"), hash_content=hash_content)),
        }
    return inventory


def inventory_differences(
    before: Mapping[str, Mapping[str, Mapping[str, Any]]],
    after: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> list[str]:
    """Compare production state while tolerating SQLite read-only sidecars.

    Opening a WAL-mode SQLite database with ``mode=ro`` can materialize a zero
    byte ``-wal`` file and the shared-memory index without changing the main
    database. A non-empty WAL, changed main file, or changed existing sidecar is
    still reported as a protected production mutation.
    """

    differences: list[str] = []
    for role in sorted(set(before) | set(after)):
        if role not in before or role not in after:
            differences.append(f"{role}:inventory membership changed")
            continue
        main_before = dict(before[role]["main"])
        main_after = dict(after[role]["main"])
        main_unchanged = main_before == main_after
        wal_before = dict(before[role]["wal"])
        wal_after = dict(after[role]["wal"])
        readonly_empty_wal = (
            main_unchanged
            and not wal_before.get("exists")
            and wal_after.get("exists")
            and wal_after.get("size") == 0
            and wal_after.get("sha256") == hashlib.sha256(b"").hexdigest()
        )
        for kind in ("main", "wal", "shm"):
            left = dict(before[role][kind])
            right = dict(after[role][kind])
            if kind == "shm" and left.get("sha256") == right.get("sha256"):
                left["mtime_ns"] = right.get("mtime_ns")
            if kind == "wal" and readonly_empty_wal:
                continue
            if kind == "shm" and readonly_empty_wal and not left.get("exists") and right.get("exists"):
                continue
            if left != right:
                differences.append(f"{role}:{kind}:{left!r} != {right!r}")
    return differences


def protected_paths() -> Iterable[Path]:
    return tuple(sorted(PROTECTED_DATABASE_PATHS))
