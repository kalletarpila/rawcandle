"""Explicit storage closeout for the two disposable P/B rehearsal owners.

This is an operator/harness helper, never a scheduler or production publisher.
``begin`` records necessity before copying; ``close`` records the final decision.
Neither CLI command deletes files. Runtime records belong in ignored Temp.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Callable

OWNERS = {
    "future": "P/B-OWNERSHIP-FUTURE-AUTO-RECONCILIATION-1",
    "no-safe-changes": "P/B-FUTURE-NO-SAFE-CHANGES-INTEGRATION-FIX",
}
SIDECARS = ("-wal", "-shm", "-journal")


def durable_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".new")
    with temporary.open("x") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def identity(path: Path, root: Path) -> dict:
    path, root = Path(path).absolute(), Path(root).absolute()
    if root.resolve() != root or path.resolve() != path or not path.is_relative_to(root):
        raise ValueError("PATH_NOT_CANONICALLY_CONFINED")
    value = path.lstat()
    if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
        raise ValueError("NOT_EXCLUSIVE_REGULAR_FILE")
    return dict(path=str(path), root=str(root), device=value.st_dev, inode=value.st_ino,
                links=value.st_nlink, logical_bytes=value.st_size,
                allocated_bytes=value.st_blocks * 512, mtime_ns=value.st_mtime_ns,
                ctime_ns=value.st_ctime_ns)


def database_files(root: Path) -> list[dict]:
    root = Path(root).absolute()
    mains = sorted(p for p in root.rglob("*") if p.suffix in (".db", ".sqlite", ".sqlite3"))
    rows = []
    for main in mains:
        rows.append(dict(identity(main, root), role="main", main_path=str(main)))
        for suffix in SIDECARS:
            sidecar = Path(str(main) + suffix)
            if sidecar.exists() or sidecar.is_symlink():
                rows.append(dict(identity(sidecar, root), role="sidecar", main_path=str(main)))
    return rows


def begin(root: Path, owner: str, record: Path, *, purpose: str,
          end_event: str, expected_allocated_bytes: int) -> dict:
    if owner not in OWNERS or not purpose.strip() or not end_event.strip():
        raise ValueError("NAMED_OWNER_PURPOSE_AND_END_EVENT_REQUIRED")
    if expected_allocated_bytes < 0:
        raise ValueError("INVALID_ALLOCATION_ESTIMATE")
    if record.exists():
        raise ValueError("BEGIN_ALREADY_RECORDED_USE_NEW_RUN")
    value = dict(owner=OWNERS[owner], root=str(root.absolute()), state="CREATED",
                 purpose=purpose, end_event=end_event,
                 expected_allocated_bytes=expected_allocated_bytes)
    durable_json(record, value)
    return value


def close(root: Path, owner: str, record: Path, *, outcome: str,
          evidence: list[Path], capability_loss: str,
          requirements: dict[str, dict] | None = None) -> dict:
    """The owner decides necessity; historical path references are not live holds.

    Requirements map exact paths to reason/owner/end_event. The caller must supply
    current live, investigation and recovery dependencies, including their closure
    over generation roles and SQLite sidecars. No receipt/DB is edited.
    """
    if owner not in OWNERS or outcome not in ("PASSED", "SUPERSEDED", "INTERRUPTED"):
        raise ValueError("EXPLICIT_OWNER_OUTCOME_REQUIRED")
    if record.exists():
        previous = json.loads(record.read_text())
        if (previous["owner"], previous["root"], previous["outcome"]) != (
                OWNERS[owner], str(root.absolute()), outcome):
            raise ValueError("CLOSEOUT_IDENTITY_CHANGED")
        if previous.get("requirements", {}) != (requirements or {}):
            raise ValueError("CLOSEOUT_REQUIREMENTS_CHANGED")
        if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != digest
               for p, digest in previous["evidence_sha256"].items()):
            raise ValueError("HISTORICAL_EVIDENCE_CHANGED")
        return previous  # Never regenerate approvals from an already retired tree.
    if not evidence or not capability_loss.strip():
        raise ValueError("COMPACT_EVIDENCE_AND_REPLAY_DISPOSITION_REQUIRED")
    seals = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in evidence}
    requirements = requirements or {}
    rows = database_files(root)
    known = {r["path"] for r in rows}
    if not set(requirements).issubset(known):
        raise ValueError("UNKNOWN_REQUIRED_PATH")
    for row in rows:
        hold = requirements.get(row["path"]) or requirements.get(row["main_path"])
        if hold:
            if any(not hold.get(k) for k in ("owner", "reason", "end_event")):
                raise ValueError("CONTINUING_NECESSITY_MUST_BE_CONCRETE")
            row.update(decision="RETAIN_REQUIRED", necessity=hold)
        elif outcome == "INTERRUPTED":
            row.update(decision="NEEDS_OWNER_DECISION", necessity="Unclosed interrupted owner operation")
        else:
            row.update(decision="RETIRE_APPROVED", capability_loss=capability_loss,
                       necessity="Owner ended disposable rehearsal; compact sealed evidence suffices")
    state = ("OWNER_DECISION_REQUIRED" if any(r["decision"] == "NEEDS_OWNER_DECISION" for r in rows)
             else "RETAIN_REQUIRED" if any(r["decision"] == "RETAIN_REQUIRED" for r in rows)
             else "ARCHIVED_EVIDENCE")
    retained = sum(r["allocated_bytes"] for r in rows if r["decision"] != "RETIRE_APPROVED")
    approved = sum(r["allocated_bytes"] for r in rows if r["decision"] == "RETIRE_APPROVED")
    value = dict(owner=OWNERS[owner], root=str(root.absolute()), outcome=outcome,
                 state=state, evidence_sha256=seals, files=rows, requirements=requirements,
                 retained_allocated_bytes=retained, retained_gb=retained / 1_000_000_000,
                 approved_allocated_bytes=approved, approved_gb=approved / 1_000_000_000,
                 executable_replay=("Intentionally unavailable after approved retirement" if state == "ARCHIVED_EVIDENCE"
                                    else "Required or unresolved executable environments remain retained"),
                 capability_loss=capability_loss)
    durable_json(record, value)
    return value


def retire_exact(row: dict, ledger: Path, *, check_live: Callable[[], None],
                 check_busy: Callable[[str], None]) -> str:
    """Exact-file primitive for an explicitly authorized, externally locked pass.

    Callbacks must establish host visibility, current references/owner recovery and
    no open/mapped SQLite users. No native acceptance state is manufactured here.
    """
    if row["decision"] != "RETIRE_APPROVED":
        raise ValueError("NOT_APPROVED")
    events = json.loads(ledger.read_text()) if ledger.exists() else {"files": {}}
    prior = events["files"].get(row["path"])
    if prior:
        if prior["outcome"] == "REMOVED" and not os.path.lexists(row["path"]):
            return "ALREADY_REMOVED"
        raise ValueError("PRIOR_ATTEMPT_REQUIRES_RECONCILIATION")
    check_live()
    check_busy(row["main_path"])
    current = identity(Path(row["path"]), Path(row["root"]))
    if any(current[key] != row[key] for key in current):
        raise ValueError("STALE_IDENTITY")
    events["files"][row["path"]] = dict(outcome="PREPARED", identity=current,
                                         decision=row["decision"])
    durable_json(ledger, events)
    # Repeat gates after the durable decision, immediately before exact unlink.
    check_live()
    check_busy(row["main_path"])
    if identity(Path(row["path"]), Path(row["root"])) != current:
        raise ValueError("STALE_IDENTITY")
    parent = Path(row["path"]).parent
    parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        pinned = os.stat(Path(row["path"]).name, dir_fd=parent_fd, follow_symlinks=False)
        if (pinned.st_dev, pinned.st_ino, pinned.st_nlink) != (row["device"], row["inode"], row["links"]):
            raise ValueError("STALE_PINNED_IDENTITY")
        if identity(Path(row["path"]), Path(row["root"])) != current:
            raise ValueError("STALE_IDENTITY")
        os.unlink(Path(row["path"]).name, dir_fd=parent_fd)
        os.fsync(parent_fd)
    except OSError as exc:
        events["files"][row["path"]]["outcome"] = "AMBIGUOUS_STOP"
        durable_json(ledger, events)
        raise RuntimeError("DO_NOT_RETRY_UNLINK") from exc
    finally:
        os.close(parent_fd)
    events["files"][row["path"]].update(outcome="REMOVED", allocated_bytes_released=row["allocated_bytes"])
    durable_json(ledger, events)
    return "REMOVED"


def run_harness(root: Path, owner: str, record: Path, harness: Callable[[], dict], *,
                purpose: str, end_event: str, expected_allocated_bytes: int) -> dict:
    """Both owners' prospective harness entry point; always report on exit.

    The harness returns outcome, compact evidence, concrete requirements and the
    accepted capability loss. An exception leaves an explicit unresolved hold.
    Existing historical harness scripts are immutable evidence, not resumed here.
    """
    creation = record.with_name(record.stem + "_creation.json")
    begin(root, owner, creation, purpose=purpose, end_event=end_event,
          expected_allocated_bytes=expected_allocated_bytes)
    try:
        result = harness()
    except BaseException:
        close(root, owner, record, outcome="INTERRUPTED", evidence=[creation],
              capability_loss="No retirement approved until interrupted owner recovery is reviewed")
        raise
    return close(root, owner, record, **result)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("begin", "close"))
    parser.add_argument("owner", choices=OWNERS)
    parser.add_argument("root", type=Path)
    parser.add_argument("record", type=Path)
    parser.add_argument("--purpose")
    parser.add_argument("--end-event")
    parser.add_argument("--expected-allocated-bytes", type=int, default=0)
    parser.add_argument("--outcome", choices=("PASSED", "SUPERSEDED", "INTERRUPTED"))
    parser.add_argument("--evidence", action="append", type=Path, default=[])
    parser.add_argument("--capability-loss")
    parser.add_argument("--requirements", type=Path)
    args = parser.parse_args()
    if args.action == "begin":
        value = begin(args.root, args.owner, args.record, purpose=args.purpose or "",
                      end_event=args.end_event or "", expected_allocated_bytes=args.expected_allocated_bytes)
    else:
        value = close(args.root, args.owner, args.record, outcome=args.outcome,
                      evidence=args.evidence, capability_loss=args.capability_loss or "",
                      requirements=json.loads(args.requirements.read_text()) if args.requirements else {})
    print(json.dumps({k: v for k, v in value.items() if k != "files"}, indent=2))


if __name__ == "__main__":
    main()
