from __future__ import annotations

import argparse
import io
import re
import sqlite3
import sys
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from dev_tools.run_datacenter_dashboard_action_summary_write import (
    main as action_summary_main,
)
from dev_tools.run_datacenter_dashboard_decision_trace_write import (
    main as decision_trace_main,
)
from dev_tools.run_datacenter_dashboard_group_enrichment_write import main as group_main
from dev_tools.run_datacenter_dashboard_ticker_decision_enrichment_write import (
    main as ticker_decision_main,
)
from dev_tools.run_datacenter_dashboard_ticker_enrichment_write import main as ticker_main


RUN_TABLE = "dc_dashboard_enrichment_run_daily"
TICKER_TABLE = "dc_dashboard_ticker_enrichment_daily"
GROUP_TABLE = "dc_dashboard_group_enrichment_daily"
ACTION_SUMMARY_TABLE = "dc_dashboard_action_summary_daily"
DECISION_TRACE_TABLE = "dc_dashboard_decision_trace_daily"
CALC_VERSION = "DATACENTER_DASHBOARD_ENRICHMENT_ORCHESTRATOR_V1"
WARNING_RE = re.compile(r"^SUMMARY [^.]+\.warning=(.*)$")
SUMMARY_RE = re.compile(r"^SUMMARY ([^.]+\..+?)=(.*)$")


class _Tee(io.StringIO):
    def __init__(self, target: io.TextIOBase) -> None:
        super().__init__()
        self._target = target

    def write(self, s: str) -> int:
        self._target.write(s)
        return super().write(s)

    def flush(self) -> None:
        self._target.flush()
        super().flush()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Datacenter dashboard enrichment writers and write run metadata."
    )
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--signal-date", required=True)
    parser.add_argument("--taxonomy-version", required=True)
    parser.add_argument(
        "--mode",
        required=True,
        choices=("insert-missing", "upsert", "replace-date"),
    )
    parser.add_argument("--run-id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--watchlist-file")
    parser.add_argument("--pullback-lookback-rows", type=int)
    parser.add_argument("--use-upstream-rolling5-pullback", action="store_true")
    parser.add_argument("--skip-ticker", action="store_true")
    parser.add_argument("--skip-group", action="store_true")
    parser.add_argument("--skip-ticker-decision", action="store_true")
    parser.add_argument("--skip-action-summary", action="store_true")
    parser.add_argument("--skip-decision-trace", action="store_true")
    return parser


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_run_id(signal_date: str, explicit_run_id: str | None) -> str:
    if explicit_run_id:
        return explicit_run_id
    return f"DC_DASH_ENRICH_{signal_date}_{_utc_now_text()}"


def _connect_read_only(db_path: str) -> sqlite3.Connection:
    normalized = db_path.strip()
    if not normalized:
        raise FileNotFoundError("analysis_db path is required")
    if not Path(normalized).exists():
        raise FileNotFoundError(f"analysis_db not found: {normalized}")
    conn = sqlite3.connect(f"file:{normalized}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _connect_read_write(db_path: str) -> sqlite3.Connection:
    normalized = db_path.strip()
    if not normalized:
        raise FileNotFoundError("analysis_db path is required")
    if not Path(normalized).exists():
        raise FileNotFoundError(f"analysis_db not found: {normalized}")
    conn = sqlite3.connect(normalized)
    conn.row_factory = sqlite3.Row
    return conn


def _normalize_signal_date(value: str) -> str:
    normalized = value.strip()
    parts = normalized.split("-")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise ValueError(f"invalid signal_date format: {normalized}")
    if len(parts[0]) != 4 or len(parts[1]) != 2 or len(parts[2]) != 2:
        raise ValueError(f"invalid signal_date format: {normalized}")
    return normalized


def _normalize_taxonomy_version(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("taxonomy_version must be non-empty")
    return normalized


def _row_count_for_selection(
    conn: sqlite3.Connection,
    table_name: str,
    signal_date: str,
    taxonomy_version: str,
) -> int:
    row = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM {table_name}
        WHERE signal_date = ? AND taxonomy_version = ?
        """,
        (signal_date, taxonomy_version),
    ).fetchone()
    return int(row[0])


def _emit_summary(name: str, value: object) -> None:
    print(f"SUMMARY datacenter_dashboard_enrichment_write.{name}={value}")


def _stage_args(
    *,
    analysis_db: str,
    signal_date: str,
    taxonomy_version: str,
    mode: str,
    run_id: str,
    dry_run: bool,
    limit: int | None,
    supports_limit: bool,
    watchlist_file: str | None = None,
    supports_watchlist_file: bool = False,
    pullback_lookback_rows: int | None = None,
    supports_pullback_lookback_rows: bool = False,
    use_upstream_rolling5_pullback: bool = False,
    supports_upstream_rolling5_pullback: bool = False,
) -> list[str]:
    args = [
        "--analysis-db",
        analysis_db,
        "--signal-date",
        signal_date,
        "--taxonomy-version",
        taxonomy_version,
        "--mode",
        mode,
        "--run-id",
        run_id,
    ]
    if dry_run:
        args.append("--dry-run")
    if supports_limit and limit is not None:
        args.extend(["--limit", str(limit)])
    if supports_watchlist_file and watchlist_file:
        args.extend(["--watchlist-file", watchlist_file])
    if supports_pullback_lookback_rows and pullback_lookback_rows is not None:
        args.extend(["--pullback-lookback-rows", str(pullback_lookback_rows)])
    if supports_upstream_rolling5_pullback and use_upstream_rolling5_pullback:
        args.append("--use-upstream-rolling5-pullback")
    return args


def _run_stage(stage_main, args: list[str]) -> tuple[int, list[str], dict[str, str]]:
    tee = _Tee(sys.stdout)
    with redirect_stdout(tee):
        exit_code = stage_main(args)
    warnings: list[str] = []
    summaries: dict[str, str] = {}
    for line in tee.getvalue().splitlines():
        summary_match = SUMMARY_RE.match(line.strip())
        if summary_match:
            summaries[summary_match.group(1)] = summary_match.group(2).strip()
        match = WARNING_RE.match(line.strip())
        if match:
            warning = match.group(1).strip()
            if warning:
                warnings.append(warning)
    return exit_code, warnings, summaries


def _write_metadata_row(
    conn: sqlite3.Connection,
    *,
    mode: str,
    run_id: str,
    signal_date: str,
    taxonomy_version: str,
    status: str,
    readiness: str,
    ticker_rows: int,
    group_rows: int,
    action_summary_rows: int,
    decision_trace_rows: int,
    warnings: str | None,
    created_at_utc: str,
) -> int:
    values = (
        run_id,
        signal_date,
        taxonomy_version,
        status,
        readiness,
        ticker_rows,
        group_rows,
        action_summary_rows,
        decision_trace_rows,
        warnings,
        CALC_VERSION,
        created_at_utc,
    )
    if mode == "insert-missing":
        exists = conn.execute(
            f"SELECT 1 FROM {RUN_TABLE} WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if exists is not None:
            return 0
        conn.execute(
            f"""
            INSERT INTO {RUN_TABLE} (
                run_id,
                signal_date,
                taxonomy_version,
                status,
                readiness,
                ticker_rows,
                group_rows,
                action_summary_rows,
                decision_trace_rows,
                warnings,
                calc_version,
                created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        return 1
    if mode == "upsert":
        conn.execute(
            f"""
            INSERT INTO {RUN_TABLE} (
                run_id,
                signal_date,
                taxonomy_version,
                status,
                readiness,
                ticker_rows,
                group_rows,
                action_summary_rows,
                decision_trace_rows,
                warnings,
                calc_version,
                created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                signal_date=excluded.signal_date,
                taxonomy_version=excluded.taxonomy_version,
                status=excluded.status,
                readiness=excluded.readiness,
                ticker_rows=excluded.ticker_rows,
                group_rows=excluded.group_rows,
                action_summary_rows=excluded.action_summary_rows,
                decision_trace_rows=excluded.decision_trace_rows,
                warnings=excluded.warnings,
                calc_version=excluded.calc_version,
                created_at_utc=excluded.created_at_utc
            """,
            values,
        )
        return 1
    conn.execute(
        f"""
        DELETE FROM {RUN_TABLE}
        WHERE signal_date = ? AND taxonomy_version = ?
        """,
        (signal_date, taxonomy_version),
    )
    conn.execute(
        f"""
        INSERT INTO {RUN_TABLE} (
            run_id,
            signal_date,
            taxonomy_version,
            status,
            readiness,
            ticker_rows,
            group_rows,
            action_summary_rows,
            decision_trace_rows,
            warnings,
            calc_version,
            created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        values,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        signal_date = _normalize_signal_date(args.signal_date)
        taxonomy_version = _normalize_taxonomy_version(args.taxonomy_version)
        if args.limit is not None and args.limit <= 0:
            raise ValueError("--limit must be greater than 0 when provided")
        if args.pullback_lookback_rows is not None and args.pullback_lookback_rows <= 0:
            raise ValueError("--pullback-lookback-rows must be greater than 0 when provided")

        run_id = _resolve_run_id(signal_date, args.run_id)
        warnings: list[str] = []

        attempted = {
            "ticker": 0 if args.skip_ticker else 1,
            "group": 0 if args.skip_group else 1,
            "ticker_decision": 0 if args.skip_ticker_decision else 1,
            "action_summary": 0 if args.skip_action_summary else 1,
            "decision_trace": 0 if args.skip_decision_trace else 1,
        }
        ticker_decision_updated_rows = ""

        stages = [
            (
                "ticker",
                ticker_main,
                _stage_args(
                    analysis_db=args.analysis_db,
                    signal_date=signal_date,
                    taxonomy_version=taxonomy_version,
                    mode=args.mode,
                    run_id=run_id,
                    dry_run=args.dry_run,
                    limit=args.limit,
                    supports_limit=True,
                    watchlist_file=args.watchlist_file,
                    supports_watchlist_file=True,
                    pullback_lookback_rows=args.pullback_lookback_rows,
                    supports_pullback_lookback_rows=True,
                    use_upstream_rolling5_pullback=args.use_upstream_rolling5_pullback,
                    supports_upstream_rolling5_pullback=True,
                ),
                TICKER_TABLE,
                bool(args.skip_ticker),
            ),
            (
                "group",
                group_main,
                _stage_args(
                    analysis_db=args.analysis_db,
                    signal_date=signal_date,
                    taxonomy_version=taxonomy_version,
                    mode=args.mode,
                    run_id=run_id,
                    dry_run=args.dry_run,
                    limit=args.limit,
                    supports_limit=True,
                ),
                GROUP_TABLE,
                bool(args.skip_group),
            ),
            (
                "ticker_decision",
                ticker_decision_main,
                _stage_args(
                    analysis_db=args.analysis_db,
                    signal_date=signal_date,
                    taxonomy_version=taxonomy_version,
                    mode="upsert" if args.mode == "insert-missing" else args.mode,
                    run_id=run_id,
                    dry_run=args.dry_run,
                    limit=args.limit,
                    supports_limit=True,
                ),
                TICKER_TABLE,
                bool(args.skip_ticker_decision),
            ),
            (
                "action_summary",
                action_summary_main,
                _stage_args(
                    analysis_db=args.analysis_db,
                    signal_date=signal_date,
                    taxonomy_version=taxonomy_version,
                    mode=args.mode,
                    run_id=run_id,
                    dry_run=args.dry_run,
                    limit=args.limit,
                    supports_limit=False,
                ),
                ACTION_SUMMARY_TABLE,
                bool(args.skip_action_summary),
            ),
            (
                "decision_trace",
                decision_trace_main,
                _stage_args(
                    analysis_db=args.analysis_db,
                    signal_date=signal_date,
                    taxonomy_version=taxonomy_version,
                    mode=args.mode,
                    run_id=run_id,
                    dry_run=args.dry_run,
                    limit=args.limit,
                    supports_limit=True,
                ),
                DECISION_TRACE_TABLE,
                bool(args.skip_decision_trace),
            ),
        ]

        for stage_name, stage_main, stage_argv, _, is_skipped in stages:
            if is_skipped:
                continue
            exit_code, stage_warnings, stage_summaries = _run_stage(stage_main, stage_argv)
            warnings.extend(stage_warnings)
            if stage_name == "ticker_decision":
                ticker_decision_updated_rows = stage_summaries.get(
                    "datacenter_dashboard_ticker_decision_enrichment_write.updated_rows",
                    "",
                )
            if exit_code != 0:
                print(f"ERROR: {stage_name} stage failed", file=sys.stderr)
                return 1

        connector = _connect_read_only if args.dry_run else _connect_read_write
        with connector(args.analysis_db) as conn:
            ticker_rows = (
                _row_count_for_selection(conn, TICKER_TABLE, signal_date, taxonomy_version)
                if attempted["ticker"]
                else 0
            )
            group_rows = (
                _row_count_for_selection(conn, GROUP_TABLE, signal_date, taxonomy_version)
                if attempted["group"]
                else 0
            )
            action_summary_rows = (
                _row_count_for_selection(conn, ACTION_SUMMARY_TABLE, signal_date, taxonomy_version)
                if attempted["action_summary"]
                else 0
            )
            decision_trace_rows = (
                _row_count_for_selection(conn, DECISION_TRACE_TABLE, signal_date, taxonomy_version)
                if attempted["decision_trace"]
                else 0
            )

            if args.dry_run:
                status = "DRY_RUN"
                readiness = "DRY_RUN"
                metadata_written = 0
            else:
                status = "OK"
                all_attempted = all(attempted.values())
                all_positive = (
                    ticker_rows > 0
                    and group_rows > 0
                    and action_summary_rows > 0
                    and decision_trace_rows > 0
                )
                readiness = "READY" if all_attempted and all_positive else "PARTIAL"
                metadata_written = _write_metadata_row(
                    conn,
                    mode=args.mode,
                    run_id=run_id,
                    signal_date=signal_date,
                    taxonomy_version=taxonomy_version,
                    status=status,
                    readiness=readiness,
                    ticker_rows=ticker_rows,
                    group_rows=group_rows,
                    action_summary_rows=action_summary_rows,
                    decision_trace_rows=decision_trace_rows,
                    warnings=",".join(dict.fromkeys(warnings)) or None,
                    created_at_utc=_utc_now_text(),
                )
                conn.commit()

        _emit_summary("status", status)
        _emit_summary("analysis_db", args.analysis_db)
        _emit_summary("signal_date", signal_date)
        _emit_summary("taxonomy_version", taxonomy_version)
        _emit_summary("mode", args.mode)
        _emit_summary("dry_run", 1 if args.dry_run else 0)
        _emit_summary("watchlist_file", args.watchlist_file or "")
        _emit_summary(
            "use_upstream_rolling5_pullback",
            1 if args.use_upstream_rolling5_pullback else 0,
        )
        _emit_summary("pullback_lookback_rows", args.pullback_lookback_rows or "")
        _emit_summary("run_id", run_id)
        _emit_summary("ticker_attempted", attempted["ticker"])
        _emit_summary("group_attempted", attempted["group"])
        _emit_summary("ticker_decision_attempted", attempted["ticker_decision"])
        _emit_summary("action_summary_attempted", attempted["action_summary"])
        _emit_summary("decision_trace_attempted", attempted["decision_trace"])
        _emit_summary("ticker_rows", ticker_rows)
        _emit_summary("group_rows", group_rows)
        _emit_summary("ticker_decision_updated_rows", ticker_decision_updated_rows)
        _emit_summary("action_summary_rows", action_summary_rows)
        _emit_summary("decision_trace_rows", decision_trace_rows)
        _emit_summary("readiness", readiness)
        _emit_summary("metadata_written", metadata_written)
        _emit_summary("warnings", ",".join(dict.fromkeys(warnings)))
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
