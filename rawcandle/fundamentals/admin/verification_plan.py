from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


ENVIRONMENTS = {"production", "copy"}
ACCESS_MODES = {"writable", "read-only", "unused"}

HEAVY_PREWRITE_CHECKS = (
    "full_integrity_quick_check",
    "full_foreign_key_check",
    "verified_backup",
    "restore_rehearsal",
)
HEAVY_POSTWRITE_CHECKS = (
    "post_write_quick_check",
    "post_write_foreign_key_check",
    "protected_logical_inventory",
    "rollback_verification",
    "writable_sidecar_cleanup",
)
TARGETED_READONLY_CHECKS = (
    "canonical_path_and_role",
    "required_schema_or_table_availability",
    "active_pointer_or_version",
    "relevant_source_fingerprint",
    "relevant_row_counts",
    "bounded_targeted_consistency_queries",
    "no_write_confirmation",
)
COPY_WRITABLE_CHECKS = (
    "copy_integrity_after_creation",
    "copy_integrity_after_apply",
    "repeat_no_change_logical_comparison",
    "rollback_restores_baseline",
)


@dataclass(frozen=True)
class DatabaseRoleDeclaration:
    semantic_role: str
    environment: str
    access_mode: str
    path: Path | None = None
    reason: str = ""

    def normalized(self) -> "DatabaseRoleDeclaration":
        environment = self.environment.strip().lower()
        access_mode = self.access_mode.strip().lower()
        semantic_role = self.semantic_role.strip().lower()
        if environment not in ENVIRONMENTS:
            raise ValueError(f"ADMIN_VERIFICATION_UNKNOWN_ENVIRONMENT:{self.environment}")
        if access_mode not in ACCESS_MODES:
            raise ValueError(f"ADMIN_VERIFICATION_UNKNOWN_ACCESS_MODE:{self.access_mode}")
        if not semantic_role:
            raise ValueError("ADMIN_VERIFICATION_EMPTY_SEMANTIC_ROLE")
        return DatabaseRoleDeclaration(
            semantic_role=semantic_role,
            environment=environment,
            access_mode=access_mode,
            path=self.path,
            reason=self.reason,
        )


@dataclass(frozen=True)
class OperationRoleContract:
    operation_name: str
    declarations: tuple[DatabaseRoleDeclaration, ...]
    write_boundary_crossed: bool = False

    @classmethod
    def from_role_sets(
        cls,
        *,
        operation_name: str,
        paths: Mapping[str, Path],
        production_writable_roles: Sequence[str] = (),
        production_readonly_roles: Sequence[str] = (),
        copy_writable_roles: Sequence[str] = (),
        copy_readonly_roles: Sequence[str] = (),
        unused_roles: Sequence[str] = (),
        write_boundary_crossed: bool = False,
    ) -> "OperationRoleContract":
        declarations: list[DatabaseRoleDeclaration] = []

        def add_many(environment: str, access_mode: str, roles: Sequence[str], reason: str) -> None:
            for role in roles:
                normalized = role.strip().lower()
                declarations.append(DatabaseRoleDeclaration(normalized, environment, access_mode, paths.get(normalized), reason))

        add_many("production", "writable", production_writable_roles, "Operation may write this production database.")
        add_many("production", "read-only", production_readonly_roles, "Operation reads this production database but does not write it.")
        add_many("copy", "writable", copy_writable_roles, "Operation mutates this isolated copy database.")
        add_many("copy", "read-only", copy_readonly_roles, "Operation reads this isolated copy database.")
        add_many("production", "unused", unused_roles, "Operation does not access this production database.")
        return cls(operation_name=operation_name, declarations=tuple(declarations), write_boundary_crossed=write_boundary_crossed)


def build_verification_plan(contract: OperationRoleContract) -> dict[str, Any]:
    seen: dict[tuple[str, str], DatabaseRoleDeclaration] = {}
    role_entries: list[dict[str, Any]] = []
    for raw in contract.declarations:
        declaration = raw.normalized()
        key = (declaration.environment, declaration.semantic_role)
        previous = seen.get(key)
        if previous is not None and previous.access_mode != declaration.access_mode:
            raise ValueError(
                "ADMIN_VERIFICATION_CONFLICTING_ROLE:"
                f"{declaration.environment}:{declaration.semantic_role}:{previous.access_mode}:{declaration.access_mode}"
            )
        seen[key] = declaration

    for declaration in sorted(seen.values(), key=lambda item: (item.environment, item.semantic_role)):
        role_entries.append(_plan_entry(declaration, write_boundary_crossed=contract.write_boundary_crossed))

    return {
        "operation_name": contract.operation_name,
        "write_boundary_crossed": contract.write_boundary_crossed,
        "roles": role_entries,
        "role_matrix": {
            "production_writable_roles": sorted(item["semantic_role"] for item in role_entries if item["environment"] == "production" and item["access_mode"] == "writable"),
            "production_readonly_roles": sorted(item["semantic_role"] for item in role_entries if item["environment"] == "production" and item["access_mode"] == "read-only"),
            "copy_writable_roles": sorted(item["semantic_role"] for item in role_entries if item["environment"] == "copy" and item["access_mode"] == "writable"),
            "copy_readonly_roles": sorted(item["semantic_role"] for item in role_entries if item["environment"] == "copy" and item["access_mode"] == "read-only"),
            "unused_roles": sorted(item["semantic_role"] for item in role_entries if item["access_mode"] == "unused"),
        },
    }


def _plan_entry(declaration: DatabaseRoleDeclaration, *, write_boundary_crossed: bool) -> dict[str, Any]:
    if declaration.environment == "production" and declaration.access_mode == "writable":
        if write_boundary_crossed:
            return _entry(
                declaration,
                preflight_checks=("canonical_path_and_role", "required_schema_or_table_availability", *HEAVY_PREWRITE_CHECKS),
                postflight_checks=HEAVY_POSTWRITE_CHECKS,
                backup_required=True,
                rollback_required=True,
                selected_reason="Production write boundary was crossed; full production write protection is required.",
                skipped_reason=None,
            )
        return _entry(
            declaration,
            preflight_checks=("canonical_path_and_role", "required_schema_or_table_availability", "write_boundary_guard"),
            postflight_checks=("targeted_no_write_confirmation",),
            backup_required=False,
            rollback_required=False,
            selected_reason="Production database is write-capable for the operation, but no production write boundary was crossed.",
            skipped_reason="Heavy post-write checks are skipped because no production write occurred.",
        )
    if declaration.environment == "production" and declaration.access_mode == "read-only":
        return _entry(
            declaration,
            preflight_checks=TARGETED_READONLY_CHECKS,
            postflight_checks=("targeted_no_write_confirmation",),
            backup_required=False,
            rollback_required=False,
            selected_reason="Production database is read-only input; targeted source identity checks are sufficient.",
            skipped_reason="Heavy integrity, backup, rollback and full inventory checks require a production write role.",
        )
    if declaration.environment == "copy" and declaration.access_mode == "writable":
        return _entry(
            declaration,
            preflight_checks=("copy_path_isolation", "copy_integrity_after_creation"),
            postflight_checks=COPY_WRITABLE_CHECKS,
            backup_required=False,
            rollback_required=True,
            selected_reason="Isolated copy database is mutated; integrity, repeat and rollback checks apply on the copy lane.",
            skipped_reason="Production backup is not required for isolated copies.",
        )
    if declaration.environment == "copy" and declaration.access_mode == "read-only":
        return _entry(
            declaration,
            preflight_checks=("copy_path_isolation", "required_schema_or_table_availability", "bounded_targeted_consistency_queries"),
            postflight_checks=("copy_no_write_confirmation",),
            backup_required=False,
            rollback_required=False,
            selected_reason="Copy database is read-only input; only targeted reader validation is required.",
            skipped_reason="Copy write integrity and rollback checks require a copy writable role.",
        )
    if declaration.access_mode == "unused":
        return _entry(
            declaration,
            preflight_checks=(),
            postflight_checks=(),
            backup_required=False,
            rollback_required=False,
            selected_reason="Database role is unused by this operation.",
            skipped_reason="No database access or verification is selected for unused roles.",
        )
    raise ValueError(f"ADMIN_VERIFICATION_UNSUPPORTED_ROLE:{declaration.environment}:{declaration.access_mode}")


def _entry(
    declaration: DatabaseRoleDeclaration,
    *,
    preflight_checks: Sequence[str],
    postflight_checks: Sequence[str],
    backup_required: bool,
    rollback_required: bool,
    selected_reason: str,
    skipped_reason: str | None,
) -> dict[str, Any]:
    return {
        "semantic_role": declaration.semantic_role,
        "environment": declaration.environment,
        "access_mode": declaration.access_mode,
        "path": str(declaration.path.resolve()) if declaration.path else None,
        "preflight_checks": list(preflight_checks),
        "postflight_checks": list(postflight_checks),
        "backup_required": backup_required,
        "rollback_required": rollback_required,
        "reason": declaration.reason or selected_reason,
        "selected_reason": selected_reason,
        "skipped_heavy_checks_reason": skipped_reason,
    }
