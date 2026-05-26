from __future__ import annotations

import argparse
import io
import re
import shutil
import sqlite3
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from dev_tools.run_datacenter_dashboard_analysis_db_export import (
    main as export_main,
)
from dev_tools.run_datacenter_dashboard_build import main as build_main
from dev_tools.run_datacenter_dashboard_enrichment_audit import main as audit_main
from dev_tools.run_datacenter_dashboard_enrichment_write import (
    main as enrichment_write_main,
)
from dev_tools.run_ecosystem_dashboard_parity_audit import (
    main as parity_audit_main,
)
from dev_tools.run_ecosystem_dashboard_parity_explain import (
    main as parity_explain_main,
)
from rawcandle.datacenter_dashboard_enrichment_migration import (
    apply_datacenter_dashboard_enrichment_migration,
)


SUMMARY_RE = re.compile(r"^SUMMARY ([^.]+\..+?)=(.*)$")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a temp-copy Datacenter dashboard enrichment smoke/parity flow "
            "without modifying the source analysis.db."
        )
    )
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--price-db", required=True)
    parser.add_argument("--reports-dir", required=True)
    parser.add_argument("--signal-date", required=True)
    parser.add_argument("--taxonomy-version", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--ecosystem-code", default="DATACENTER")
    parser.add_argument("--keep-work-dir", action="store_true")
    parser.add_argument("--skip-html", action="store_true")
    parser.add_argument("--skip-parity-explain", action="store_true")
    parser.add_argument("--apply-migrations-to-copy", action="store_true")
    parser.add_argument("--watchlist-file")
    return parser


def _emit_summary(name: str, value: object) -> None:
    print(f"SUMMARY datacenter_dashboard_enrichment_e2e_smoke.{name}={value}")


def _parse_summary_lines(text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in text.splitlines():
        match = SUMMARY_RE.match(line.strip())
        if match:
            parsed[match.group(1)] = match.group(2)
    return parsed


def _validate_existing_file(path_text: str, label: str) -> Path:
    path = Path(path_text)
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"{label} is not a file: {path}")
    return path


def _validate_existing_dir(path_text: str, label: str) -> Path:
    path = Path(path_text)
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")
    if not path.is_dir():
        raise FileNotFoundError(f"{label} is not a directory: {path}")
    return path


def _prepare_work_dir(path_text: str) -> Path:
    work_dir = Path(path_text)
    work_dir.mkdir(parents=True, exist_ok=True)
    if not work_dir.is_dir():
        raise NotADirectoryError(f"work_dir is not a directory: {work_dir}")
    return work_dir


def _run_logged_step(
    *,
    step_name: str,
    step_main,
    argv: list[str],
    log_path: Path,
) -> tuple[int, dict[str, str], str, str]:
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    try:
        with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
            exit_code = int(step_main(argv))
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        exit_code = int(code)
    except Exception as exc:  # pragma: no cover - defensive wrapper
        stderr_buffer.write(f"ERROR: {step_name} raised {type(exc).__name__}: {exc}\n")
        exit_code = 1

    stdout_text = stdout_buffer.getvalue()
    stderr_text = stderr_buffer.getvalue()
    log_path.write_text(
        stdout_text
        + ("\n" if stdout_text and not stdout_text.endswith("\n") else "")
        + stderr_text,
        encoding="utf-8",
    )
    return exit_code, _parse_summary_lines(stdout_text), stdout_text, stderr_text


def _require_step_ok(
    *,
    step_name: str,
    result: tuple[int, dict[str, str], str, str],
) -> dict[str, str]:
    exit_code, summaries, _, stderr_text = result
    if exit_code != 0:
        message = stderr_text.strip() or f"{step_name} failed"
        raise RuntimeError(f"{step_name} failed: {message}")
    return summaries


def _summary_value(
    summaries: dict[str, str],
    key: str,
    default: str = "",
) -> str:
    return summaries.get(key, default)


def _apply_migrations_to_copy(copied_db: Path, log_path: Path) -> None:
    with sqlite3.connect(copied_db) as conn:
        apply_datacenter_dashboard_enrichment_migration(conn)
        conn.commit()
    log_path.write_text(
        "\n".join(
            [
                "copy_migrations_status=OK",
                f"copied_db={copied_db}",
                "migration_helper=apply_datacenter_dashboard_enrichment_migration",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        analysis_db = _validate_existing_file(args.analysis_db, "analysis_db")
        price_db = _validate_existing_file(args.price_db, "price_db")
        reports_dir = _validate_existing_dir(args.reports_dir, "reports_dir")
        watchlist_file = (
            _validate_existing_file(args.watchlist_file, "watchlist_file")
            if args.watchlist_file
            else None
        )
        work_dir = _prepare_work_dir(args.work_dir)
        copied_db = work_dir / f"analysis_enrichment_smoke_{args.signal_date}.db"
        enrichment_json = (
            work_dir / f"datacenter_dashboard_enrichment_export_{args.signal_date}.json"
        )
        enrichment_dashboard_db = (
            work_dir / f"enrichment_dashboard_{args.signal_date}.db"
        )
        reports_dashboard_db = work_dir / f"reports_dashboard_{args.signal_date}.db"
        enrichment_html = (
            work_dir / f"datacenter_dashboard_enrichment_{args.signal_date}.html"
        )
        reports_html = (
            work_dir
            / f"datacenter_dashboard_reports_reference_{args.signal_date}.html"
        )
        enrichment_run_id = f"DC_DASH_ENRICH_SMOKE_{args.signal_date}"

        shutil.copy2(analysis_db, copied_db)
        copy_migration_status = "SKIPPED"
        if args.apply_migrations_to_copy:
            _apply_migrations_to_copy(
                copied_db,
                work_dir / "copy_migrations.log",
            )
            copy_migration_status = "OK"

        enrichment_write_summaries = _require_step_ok(
            step_name="enrichment_write",
            result=_run_logged_step(
                step_name="enrichment_write",
                step_main=enrichment_write_main,
                argv=[
                    "--analysis-db",
                    str(copied_db),
                    "--signal-date",
                    args.signal_date,
                    "--taxonomy-version",
                    args.taxonomy_version,
                    "--mode",
                    "replace-date",
                    "--run-id",
                    enrichment_run_id,
                ]
                + (
                    ["--watchlist-file", str(watchlist_file)]
                    if watchlist_file is not None
                    else []
                ),
                log_path=work_dir / "enrichment_write.log",
            ),
        )

        enrichment_audit_summaries = _require_step_ok(
            step_name="enrichment_audit",
            result=_run_logged_step(
                step_name="enrichment_audit",
                step_main=audit_main,
                argv=[
                    "--analysis-db",
                    str(copied_db),
                    "--signal-date",
                    args.signal_date,
                    "--taxonomy-version",
                    args.taxonomy_version,
                ],
                log_path=work_dir / "enrichment_audit.log",
            ),
        )

        enrichment_export_summaries = _require_step_ok(
            step_name="enrichment_export",
            result=_run_logged_step(
                step_name="enrichment_export",
                step_main=export_main,
                argv=[
                    "--analysis-db",
                    str(copied_db),
                    "--price-db",
                    str(price_db),
                    "--ecosystem-code",
                    args.ecosystem_code,
                    "--report-date",
                    args.signal_date,
                    "--source-mode",
                    "enrichment",
                    "--output-json",
                    str(enrichment_json),
                    "--taxonomy-version",
                    args.taxonomy_version,
                ],
                log_path=work_dir / "enrichment_export.log",
            ),
        )

        enrichment_build_argv = [
            "--dashboard-db",
            str(enrichment_dashboard_db),
            "--report-date",
            args.signal_date,
            "--input-mode",
            "structured",
            "--structured-input-json",
            str(enrichment_json),
            "--mode",
            "replace-date",
        ]
        if not args.skip_html:
            enrichment_build_argv.extend(
                ["--render-html", "--html-output", str(enrichment_html)]
            )
        enrichment_build_summaries = _require_step_ok(
            step_name="enrichment_build",
            result=_run_logged_step(
                step_name="enrichment_build",
                step_main=build_main,
                argv=enrichment_build_argv,
                log_path=work_dir / "enrichment_build.log",
            ),
        )

        reports_build_argv = [
            "--dashboard-db",
            str(reports_dashboard_db),
            "--report-date",
            args.signal_date,
            "--input-mode",
            "reports",
            "--reports-dir",
            str(reports_dir),
            "--mode",
            "replace-date",
        ]
        if not args.skip_html:
            reports_build_argv.extend(["--render-html", "--html-output", str(reports_html)])
        reports_build_summaries = _require_step_ok(
            step_name="reports_build",
            result=_run_logged_step(
                step_name="reports_build",
                step_main=build_main,
                argv=reports_build_argv,
                log_path=work_dir / "reports_build.log",
            ),
        )

        reports_run_id = _summary_value(
            reports_build_summaries,
            "ecosystem_dashboard_build.run_id",
        )
        selected_enrichment_run_id = _summary_value(
            enrichment_build_summaries,
            "ecosystem_dashboard_build.run_id",
            enrichment_run_id,
        )

        parity_audit_summaries = _require_step_ok(
            step_name="parity_audit",
            result=_run_logged_step(
                step_name="parity_audit",
                step_main=parity_audit_main,
                argv=[
                    "--left-dashboard-db",
                    str(reports_dashboard_db),
                    "--left-run-id",
                    reports_run_id,
                    "--right-dashboard-db",
                    str(enrichment_dashboard_db),
                    "--right-run-id",
                    selected_enrichment_run_id,
                    "--ecosystem-code",
                    args.ecosystem_code,
                    "--report-date",
                    args.signal_date,
                    "--left-label",
                    "reports",
                    "--right-label",
                    "enrichment",
                ],
                log_path=work_dir / "parity_audit.log",
            ),
        )

        if not args.skip_parity_explain:
            _require_step_ok(
                step_name="parity_explain",
                result=_run_logged_step(
                    step_name="parity_explain",
                    step_main=parity_explain_main,
                    argv=[
                        "--left-dashboard-db",
                        str(reports_dashboard_db),
                        "--left-run-id",
                        reports_run_id,
                        "--right-dashboard-db",
                        str(enrichment_dashboard_db),
                        "--right-run-id",
                        selected_enrichment_run_id,
                        "--ecosystem-code",
                        args.ecosystem_code,
                        "--report-date",
                        args.signal_date,
                        "--left-label",
                        "reports",
                        "--right-label",
                        "enrichment",
                    ],
                    log_path=work_dir / "parity_explain.log",
                ),
            )

        _emit_summary("status", "OK")
        _emit_summary(
            "apply_migrations_to_copy",
            1 if args.apply_migrations_to_copy else 0,
        )
        _emit_summary("copy_migration_status", copy_migration_status)
        _emit_summary("analysis_db_source", str(analysis_db))
        _emit_summary("analysis_db_copy", str(copied_db))
        _emit_summary("price_db", str(price_db))
        _emit_summary("reports_dir", str(reports_dir))
        _emit_summary("watchlist_file", str(watchlist_file) if watchlist_file else "")
        _emit_summary("signal_date", args.signal_date)
        _emit_summary("taxonomy_version", args.taxonomy_version)
        _emit_summary("work_dir", str(work_dir))
        _emit_summary(
            "enrichment_readiness",
            _summary_value(
                enrichment_audit_summaries,
                "datacenter_dashboard_enrichment_audit.readiness",
                "UNKNOWN",
            ),
        )
        _emit_summary("enrichment_json", str(enrichment_json))
        _emit_summary("enrichment_dashboard_db", str(enrichment_dashboard_db))
        _emit_summary("reports_dashboard_db", str(reports_dashboard_db))
        _emit_summary("enrichment_run_id", selected_enrichment_run_id)
        _emit_summary("reports_run_id", reports_run_id)
        _emit_summary("enrichment_html", "" if args.skip_html else str(enrichment_html))
        _emit_summary("reports_html", "" if args.skip_html else str(reports_html))
        _emit_summary(
            "parity_sections_with_count_diff",
            _summary_value(
                parity_audit_summaries,
                "ecosystem_dashboard_parity_audit.sections_with_count_diff",
            ),
        )
        _emit_summary(
            "parity_key_differences",
            _summary_value(
                parity_audit_summaries,
                "ecosystem_dashboard_parity_audit.key_differences",
            ),
        )
        _emit_summary(
            "parity_field_differences",
            _summary_value(
                parity_audit_summaries,
                "ecosystem_dashboard_parity_audit.field_differences",
            ),
        )

        _emit_summary(
            "reports_source_reports",
            _summary_value(
                reports_build_summaries,
                "ecosystem_dashboard_build.source_reports_count",
            ),
        )
        _emit_summary("reports_action_summary", "")
        _emit_summary(
            "reports_market_map",
            _summary_value(
                reports_build_summaries,
                "ecosystem_dashboard_build.market_map_rows",
            ),
        )
        _emit_summary(
            "reports_watchlist",
            _summary_value(
                reports_build_summaries,
                "ecosystem_dashboard_build.watchlist_rows",
            ),
        )
        _emit_summary(
            "reports_tickers",
            _summary_value(
                reports_build_summaries,
                "ecosystem_dashboard_build.ticker_rows",
            ),
        )
        _emit_summary(
            "reports_decision_trace",
            _summary_value(
                reports_build_summaries,
                "ecosystem_dashboard_build.trace_rows",
            ),
        )

        _emit_summary(
            "enrichment_source_reports",
            _summary_value(
                enrichment_build_summaries,
                "ecosystem_dashboard_build.source_reports_count",
            ),
        )
        _emit_summary(
            "enrichment_action_summary",
            _summary_value(
                enrichment_export_summaries,
                "datacenter_dashboard_analysis_db_export.action_summary",
            ),
        )
        _emit_summary(
            "enrichment_market_map",
            _summary_value(
                enrichment_build_summaries,
                "ecosystem_dashboard_build.market_map_rows",
            ),
        )
        _emit_summary(
            "enrichment_watchlist",
            _summary_value(
                enrichment_build_summaries,
                "ecosystem_dashboard_build.watchlist_rows",
            ),
        )
        _emit_summary(
            "enrichment_tickers",
            _summary_value(
                enrichment_build_summaries,
                "ecosystem_dashboard_build.ticker_rows",
            ),
        )
        _emit_summary(
            "enrichment_decision_trace",
            _summary_value(
                enrichment_build_summaries,
                "ecosystem_dashboard_build.trace_rows",
            ),
        )
        return 0
    except (FileNotFoundError, NotADirectoryError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
