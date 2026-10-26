"""Forecast-owned latest-good backup lifecycle; unknown artifacts are never swept.

The owner record is a pointer, recovery pins and durable retirement intents, not
an archive. Data/manifest publication precedes pointer promotion; unlink always
follows revalidation of the accepted replacement. All state edits hold the
backup-directory flock. Callers also hold the source/target daily writer lock.
"""
from __future__ import annotations

import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import tempfile
import uuid
from contextlib import closing, contextmanager
from typing import Any

from rawcandle.forecasts.schema import SCHEMA_VERSION
from rawcandle.io_atomic import write_text_atomic

POLICY = "LATEST_GOOD_BACKUP_ONLY"
OWNER = ".forecast-backup-owner.json"


def checkpoint(phase: str) -> None:
    """Fault-injection boundary used by lifecycle crash tests."""


def sync_directory(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def identity(path: Path) -> dict[str, int]:
    info = path.lstat()
    if (path.absolute() != path.resolve() or not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid() or info.st_nlink != 1
            or info.st_dev != path.parent.stat().st_dev):
        raise ValueError(f"unsafe backup artifact: {path}")
    return {key: int(getattr(info, "st_" + key)) for key in ("dev", "ino", "size", "mtime_ns")}


def manifest_path(path: Path) -> Path:
    return Path(str(path) + ".manifest.json") if path.suffix == ".gz" else path.with_suffix(".manifest.json")


@contextmanager
def directory_lock(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    if directory.absolute() != directory.resolve():
        raise ValueError("backup directory must not contain symlink aliases")
    fd = os.open(directory / ".forecast-backup.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def read_owner(directory: Path) -> dict[str, Any]:
    path = directory / OWNER
    if not path.exists() and not path.is_symlink():
        return {"version": 1, "policy": POLICY, "source_path": None, "last_good": None, "pins": {}, "retire": []}
    identity(path)
    data = json.loads(path.read_text())
    if data.get("version") != 1 or data.get("policy") != POLICY:
        raise ValueError("unsupported forecast backup owner state")
    return data


def write_owner(directory: Path, state: dict[str, Any]) -> None:
    write_text_atomic(directory / OWNER, json.dumps(state, sort_keys=True, indent=2) + "\n")
    sync_directory(directory)


def describe(path: Path) -> dict[str, Any]:
    paired = manifest_path(path)
    return {"path": str(path), "identity": identity(path), "sha256": sha256(path),
            "manifest_path": str(paired), "manifest_identity": identity(paired), "manifest_sha256": sha256(paired)}


def check_description(spec: dict[str, Any], *, missing_ok: bool = False) -> None:
    for prefix in ("", "manifest_"):
        path = Path(spec[prefix + "path"])
        if missing_ok and not path.exists() and not path.is_symlink():
            continue
        if identity(path) != spec[prefix + "identity"] or sha256(path) != spec[prefix + "sha256"]:
            raise ValueError(f"backup identity changed: {path}")


def database_check(path: Path) -> dict[str, Any]:
    from rawcandle.forecasts.hardening import _core_counts
    if not path.is_file():
        raise FileNotFoundError(path)
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        quick = [row[0] for row in db.execute("PRAGMA quick_check")]
        fk = list(db.execute("PRAGMA foreign_key_check"))
        version = db.execute("SELECT version FROM forecast_schema_version WHERE db_name='forecasts'").fetchone()
        counts = _core_counts(db)
    if quick != ["ok"] or fk or not version or version[0] != SCHEMA_VERSION:
        raise ValueError("forecast backup SQLite qualification failed")
    return {"quick_check": "ok", "foreign_key_violations": 0, "schema_version": version[0], "core_counts": counts}


def decoded_digest(path: Path, expected_size: int) -> str:
    digest = hashlib.sha256()
    size = 0
    with gzip.open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(block)
            if size > expected_size:
                raise ValueError("compressed backup exceeds qualified size")
            digest.update(block)
    if size != expected_size:
        raise ValueError("compressed backup size mismatch")
    return digest.hexdigest()


def validate(path: Path) -> dict[str, Any]:
    identity(path)
    paired = manifest_path(path)
    identity(paired)
    manifest = json.loads(paired.read_text())
    if manifest.get("backup_path") != str(path.resolve()) or manifest.get("backup_fingerprint_sha256") != sha256(path):
        raise ValueError("backup manifest binding/hash mismatch")
    if manifest.get("backup_size_bytes") != path.stat().st_size:
        raise ValueError("backup size mismatch")
    if path.suffix == ".gz":
        if manifest.get("contract_version") != "forecast_backup_v2_gzip" or manifest.get("compression") != "gzip":
            raise ValueError("unsupported compressed backup")
        if (manifest.get("quick_check") != "ok" or manifest.get("foreign_key_violations") != 0
                or manifest.get("source_schema_version") != SCHEMA_VERSION
                or decoded_digest(path, manifest["uncompressed_size_bytes"]) != manifest["uncompressed_sha256"]):
            raise ValueError("compressed backup roundtrip qualification failed")
    else:
        if manifest.get("contract_version") != "forecast_backup_v1":
            raise ValueError("unsupported legacy backup")
        checked = database_check(path)
        if checked["core_counts"] != manifest.get("core_counts"):
            raise ValueError("legacy backup counts mismatch")
    return manifest


def _exclusive(path: Path):
    return os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb")


def create_locked(source: Path, directory: Path, created: str, name: str, *, promote: bool) -> dict[str, Any]:
    """Caller holds source daily lock and directory_lock."""
    state = read_owner(directory)
    if promote and state["source_path"] not in (None, str(source.resolve())):
        raise ValueError("backup directory belongs to a different forecast database")
    if state["last_good"]:
        check_description(state["last_good"])
        validate(Path(state["last_good"]["path"]))
    checked = database_check(source)
    source_before = identity(source)
    source_hash = sha256(source)
    image = directory / (name + ".gz")
    plain = directory / (name + ".creating")
    packed = Path(str(image) + ".creating")
    paired = manifest_path(image)
    artifacts = [plain, packed, image, paired]
    if any(path.exists() or path.is_symlink() for path in artifacts):
        raise FileExistsError(image)
    token = uuid.uuid4().hex
    state["source_path"] = state["source_path"] or str(source.resolve())
    state["pins"][image.name] = {"token": token, "reason": "RUN_IN_PROGRESS" if not promote else "CREATING", "artifacts": [str(p) for p in artifacts]}
    write_owner(directory, state)
    checkpoint("pin_persisted")
    owned: list[Path] = []
    try:
        with _exclusive(plain):
            pass
        owned.append(plain)
        with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as src:
            with closing(sqlite3.connect(plain)) as dst:
                src.backup(dst)
        with plain.open("rb") as stream:
            os.fsync(stream.fileno())
        checkpoint("sqlite_created")
        copied = database_check(plain)
        if copied != checked or identity(source) != source_before or sha256(source) != source_hash:
            raise ValueError("forecast source changed while backing up")
        uncompressed_hash = sha256(plain)
        size = plain.stat().st_size
        checkpoint("sqlite_verified")
        with _exclusive(packed) as output:
            owned.append(packed)
            with plain.open("rb") as input_stream, gzip.GzipFile(filename="", mode="wb", fileobj=output, compresslevel=6, mtime=0) as compressed:
                shutil.copyfileobj(input_stream, compressed, 1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        checkpoint("gzip_created")
        if decoded_digest(packed, size) != uncompressed_hash:
            raise ValueError("gzip roundtrip failed")
        checkpoint("gzip_verified")
        os.replace(packed, image)
        owned.remove(packed)
        owned.append(image)
        image.chmod(0o444)
        sync_directory(directory)
        checkpoint("image_published")
        manifest = {
            "contract_version": "forecast_backup_v2_gzip", "compression": "gzip", "compression_level": 6,
            "created_at_utc": created, "source_path": str(source.resolve()),
            "source_schema_version": SCHEMA_VERSION, "source_size_bytes": source_before["size"],
            "source_fingerprint_sha256": source_hash, "backup_path": str(image),
            "backup_size_bytes": image.stat().st_size, "backup_fingerprint_sha256": sha256(image),
            "uncompressed_size_bytes": size, "uncompressed_sha256": uncompressed_hash,
            "quick_check": "ok", "foreign_key_violations": 0, "core_counts": copied["core_counts"],
        }
        with _exclusive(paired) as output:
            owned.append(paired)
            output.write((json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode())
            output.flush()
            os.fsync(output.fileno())
        paired.chmod(0o444)
        sync_directory(directory)
        checkpoint("manifest_published")
        validate(image)
        plain.unlink()
        owned.remove(plain)
        sync_directory(directory)
    except Exception:
        for path in reversed(owned):
            path.unlink(missing_ok=True)
        state["pins"].pop(image.name, None)
        write_owner(directory, state)
        raise
    # A failure from here must preserve the fully published candidate and pin.
    if promote:
        promote_locked(directory, image, {"kind": "MANUAL_QUALIFIED_BACKUP", "accepted_at_utc": created})
    return manifest | {"manifest_path": str(paired), "recovery_pin_token": token}


def promote_locked(directory: Path, image: Path, acceptance: dict[str, Any]) -> None:
    state = read_owner(directory)
    validate(image)
    spec = describe(image)
    previous = state["last_good"]
    if previous and previous["path"] != str(image):
        check_description(previous)
        validate(Path(previous["path"]))
        if previous not in state["retire"]:
            state["retire"].append(previous)
    checkpoint("before_promotion")
    state["last_good"] = spec
    state["acceptance"] = acceptance
    if state["pins"].get(image.name, {}).get("reason") in {"CREATING", "RUN_IN_PROGRESS"}:
        state["pins"].pop(image.name, None)
    write_owner(directory, state)
    checkpoint("promoted")


def pin(backup: Path, reason: str) -> str:
    directory = backup.parent
    with directory_lock(directory):
        validate(backup)
        state = read_owner(directory)
        # Never replace another incomplete operation's pin.
        if backup.name in state["pins"]:
            raise RuntimeError("backup already recovery-pinned")
        token = uuid.uuid4().hex
        state["pins"][backup.name] = {"token": token, "reason": reason, "artifacts": [str(backup), str(manifest_path(backup))]}
        write_owner(directory, state)
        return token


def unpin(backup: Path, token: str) -> None:
    with directory_lock(backup.parent):
        state = read_owner(backup.parent)
        if state["pins"].get(backup.name, {}).get("token") != token:
            raise ValueError("recovery pin ownership mismatch")
        del state["pins"][backup.name]
        write_owner(backup.parent, state)


def _closed(paths: list[Path]) -> None:
    result = subprocess.run(["lsof", "-t", "--", *map(str, paths)], capture_output=True, text=True, check=False)
    if result.returncode not in (0, 1) or result.stdout.strip():
        raise RuntimeError("backup artifact is open or open-reference check failed")


def retention_locked(directory: Path, *, apply: bool) -> dict[str, Any]:
    state = read_owner(directory)
    good = state["last_good"]
    if good:
        check_description(good)
        validate(Path(good["path"]))
    pinned = {path for pin_data in state["pins"].values() for path in pin_data["artifacts"]}
    current = {good["path"], good["manifest_path"]} if good else set()
    eligible = []
    for spec in state["retire"]:
        paths = [Path(spec["path"]), Path(spec["manifest_path"])]
        if good and not any(str(p) in pinned | current for p in paths):
            check_description(spec, missing_ok=True)
            eligible.append(spec)
    selected = {spec[key] for spec in eligible for key in ("path", "manifest_path")}
    inventory = []
    for path in sorted(directory.iterdir()):
        if path.name in (OWNER, ".forecast-backup.lock"):
            continue
        label = ("KEEP_RECOVERY_PINNED" if str(path) in pinned else
                 "KEEP_CURRENT_LAST_GOOD" if str(path) in current else
                 "SAFE_TO_DELETE" if str(path) in selected else "UNKNOWN_KEEP")
        inventory.append({"path": str(path), "classification": label, "size_bytes": path.lstat().st_size})
    result = {"policy": POLICY, "mode": "APPLY" if apply else "DRY_RUN", "inventory": inventory,
              "selected_files": sum(row["classification"] == "SAFE_TO_DELETE" for row in inventory),
              "selected_bytes": sum(row["size_bytes"] for row in inventory if row["classification"] == "SAFE_TO_DELETE"),
              "newest_valid_backup": good and good["path"], "deleted_backups": 0, "deleted_files": []}
    if apply:
        for spec in eligible:
            # Revalidate the replacement immediately before every pair deletion.
            check_description(good)
            check_description(spec, missing_ok=True)
            paths = [Path(spec["path"]), Path(spec["manifest_path"])]
            _closed([p for p in paths if p.exists()])
            checkpoint("before_unlink")
            for path in paths:
                if path.exists():
                    path.unlink()
                    sync_directory(directory)
                    result["deleted_files"].append(str(path))
                checkpoint("artifact_unlinked")
            state["retire"].remove(spec)
            write_owner(directory, state)
            result["deleted_backups"] += 1
        result["remaining_newest_valid_backup"] = good and good["path"]
    return result


def authorize_legacy_retirement(directory: Path, reviewed: list[dict[str, Any]]) -> None:
    """Explicit operator migration only: exact, independently reviewed identities.

    No filename/age inference. The caller must establish closed recovery
    obligations and accepted-history coverage before supplying this allowlist.
    """
    with directory_lock(directory):
        state = read_owner(directory)
        if not state["last_good"]:
            raise ValueError("a qualified latest-good backup is required")
        check_description(state["last_good"])
        validate(Path(state["last_good"]["path"]))
        for spec in reviewed:
            if Path(spec["path"]).parent != directory or Path(spec["manifest_path"]).parent != directory:
                raise ValueError("retirement outside forecast backup directory")
            if spec["path"] == state["last_good"]["path"] or Path(spec["path"]).name in state["pins"]:
                raise ValueError("cannot retire protected backup")
            check_description(spec)
            validate(Path(spec["path"]))
            if spec not in state["retire"]:
                state["retire"].append(spec)
        write_owner(directory, state)


@contextmanager
def materialize(backup: Path, directory: Path):
    manifest = validate(backup)
    if backup.suffix != ".gz":
        yield backup
        return
    fd, name = tempfile.mkstemp(prefix="forecast-materialized-", suffix=".db", dir=directory)
    try:
        with os.fdopen(fd, "wb") as output, gzip.open(backup, "rb") as source:
            size = 0
            digest = hashlib.sha256()
            for block in iter(lambda: source.read(1024 * 1024), b""):
                size += len(block)
                if size > manifest["uncompressed_size_bytes"]:
                    raise ValueError("backup decompression exceeds qualified size")
                output.write(block)
                digest.update(block)
            output.flush()
            os.fsync(output.fileno())
        if size != manifest["uncompressed_size_bytes"] or digest.hexdigest() != manifest["uncompressed_sha256"]:
            raise ValueError("materialized backup hash mismatch")
        checked = database_check(Path(name))
        if checked["core_counts"] != manifest["core_counts"]:
            raise ValueError("materialized backup count mismatch")
        yield Path(name)
    finally:
        Path(name).unlink(missing_ok=True)
