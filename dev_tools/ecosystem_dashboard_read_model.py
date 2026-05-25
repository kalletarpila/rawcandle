from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from dev_tools.inspect_ecosystem_dashboard import (
    ACTION_ORDER,
    MARKET_LEVEL_ORDER,
    _connect_read_only,
    _require_tables,
)
from dev_tools.run_datacenter_dashboard_html import _REPORT_DATE_RE


@dataclass(frozen=True)
class EcosystemDashboardRunRef:
    ecosystem_code: str
    report_date: str
    run_id: str
    mode: str | None
    status: str | None
    source_report_count: int | None
    created_at_utc: str | None


@dataclass(frozen=True)
class EcosystemDashboardSnapshot:
    run: EcosystemDashboardRunRef
    source_reports: list[dict[str, object]]
    action_summary: list[dict[str, object]]
    market_map: list[dict[str, object]]
    watchlist: list[dict[str, object]]
    tickers: list[dict[str, object]]
    decision_trace: list[dict[str, object]]


def _normalize_report_date(report_date: str | None) -> str | None:
    if report_date is None:
        return None
    normalized = report_date.strip()
    if not _REPORT_DATE_RE.match(normalized):
        raise ValueError(f"invalid report_date format: {normalized}")
    return normalized


def _connect_dashboard_read_only(dashboard_db: str) -> sqlite3.Connection:
    db_path = Path(dashboard_db)
    if not db_path.exists():
        raise ValueError(f"dashboard_db not found: {dashboard_db}")
    conn = _connect_read_only(str(db_path))
    conn.row_factory = sqlite3.Row
    _require_tables(conn)
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict[str, object]:
    return {key: row[key] for key in row.keys()}


def _action_sort_key(action: object) -> tuple[int, str]:
    normalized = "" if action is None else str(action).strip().upper()
    if normalized in ACTION_ORDER:
        return (ACTION_ORDER.index(normalized), normalized)
    return (len(ACTION_ORDER), normalized)


def _market_level_sort_key(level: object) -> tuple[int, str]:
    normalized = "" if level is None else str(level).strip().upper()
    if normalized in MARKET_LEVEL_ORDER:
        return (MARKET_LEVEL_ORDER.index(normalized), normalized)
    return (len(MARKET_LEVEL_ORDER), normalized)


def _run_ref_from_row(row: sqlite3.Row) -> EcosystemDashboardRunRef:
    return EcosystemDashboardRunRef(
        ecosystem_code=row["ecosystem_code"],
        report_date=row["report_date"],
        run_id=row["run_id"],
        mode=row["selection_mode"],
        status=row["readiness"],
        source_report_count=row["source_reports_count"],
        created_at_utc=row["created_at_utc"],
    )


def resolve_dashboard_run(
    dashboard_db: str,
    ecosystem_code: str,
    report_date: str | None = None,
    run_id: str | None = None,
) -> EcosystemDashboardRunRef:
    normalized_report_date = _normalize_report_date(report_date)
    with _connect_dashboard_read_only(dashboard_db) as conn:
        if run_id is not None:
            row = conn.execute(
                """
                SELECT *
                FROM ecosystem_dashboard_runs
                WHERE ecosystem_code = ? AND run_id = ?
                """,
                (ecosystem_code, run_id),
            ).fetchone()
            if row is None:
                raise ValueError(
                    f"run_id not found for ecosystem_code={ecosystem_code}: {run_id}"
                )
            if (
                normalized_report_date is not None
                and row["report_date"] != normalized_report_date
            ):
                raise ValueError(
                    "run_id/report_date mismatch: "
                    f"run_id={run_id} has report_date={row['report_date']}, "
                    f"expected {normalized_report_date}"
                )
            return _run_ref_from_row(row)

        if normalized_report_date is None:
            raise ValueError("either run_id or report_date is required")

        row = conn.execute(
            """
            SELECT *
            FROM ecosystem_dashboard_runs
            WHERE ecosystem_code = ? AND report_date = ?
            ORDER BY created_at_utc DESC, run_id DESC
            LIMIT 1
            """,
            (ecosystem_code, normalized_report_date),
        ).fetchone()
        if row is None:
            raise ValueError(
                f"no dashboard run found for ecosystem_code={ecosystem_code} "
                f"report_date={normalized_report_date}"
            )
        return _run_ref_from_row(row)


def _load_source_reports(conn: sqlite3.Connection, run: EcosystemDashboardRunRef) -> list[dict[str, object]]:
    rows = list(
        conn.execute(
            """
            SELECT *
            FROM ecosystem_dashboard_source_reports
            WHERE ecosystem_code = ? AND report_date = ? AND run_id = ?
            """,
            (run.ecosystem_code, run.report_date, run.run_id),
        ).fetchall()
    )
    rows.sort(
        key=lambda row: (
            "" if row["markdown_path"] is None else str(row["markdown_path"]),
            "" if row["csv_path"] is None else str(row["csv_path"]),
            str(row["horizon"]),
            str(row["report_kind"]),
        )
    )
    return [_row_to_dict(row) for row in rows]


def _load_action_summary(conn: sqlite3.Connection, run: EcosystemDashboardRunRef) -> list[dict[str, object]]:
    rows = list(
        conn.execute(
            """
            SELECT *
            FROM ecosystem_dashboard_action_summary
            WHERE ecosystem_code = ? AND run_id = ?
            """,
            (run.ecosystem_code, run.run_id),
        ).fetchall()
    )
    rows.sort(key=lambda row: _action_sort_key(row["action"]))
    return [_row_to_dict(row) for row in rows]


def _load_market_map(conn: sqlite3.Connection, run: EcosystemDashboardRunRef) -> list[dict[str, object]]:
    rows = list(
        conn.execute(
            """
            SELECT *
            FROM ecosystem_dashboard_market_map
            WHERE ecosystem_code = ? AND report_date = ? AND run_id = ?
            """,
            (run.ecosystem_code, run.report_date, run.run_id),
        ).fetchall()
    )
    rows.sort(
        key=lambda row: (
            _market_level_sort_key(row["market_level"]),
            1 if row["layer"] in (None, "") else 0,
            "" if row["layer"] is None else str(row["layer"]),
            1 if row["subindustry"] in (None, "") else 0,
            "" if row["subindustry"] is None else str(row["subindustry"]),
            str(row["name"]),
        )
    )
    return [_row_to_dict(row) for row in rows]


def _load_watchlist(conn: sqlite3.Connection, run: EcosystemDashboardRunRef) -> list[dict[str, object]]:
    rows = list(
        conn.execute(
            """
            SELECT *
            FROM ecosystem_dashboard_watchlist_status
            WHERE ecosystem_code = ? AND report_date = ? AND run_id = ?
            """,
            (run.ecosystem_code, run.report_date, run.run_id),
        ).fetchall()
    )
    rows.sort(key=lambda row: (_action_sort_key(row["action"]), str(row["ticker"])))
    return [_row_to_dict(row) for row in rows]


def _load_tickers(conn: sqlite3.Connection, run: EcosystemDashboardRunRef) -> list[dict[str, object]]:
    rows = list(
        conn.execute(
            """
            SELECT *
            FROM ecosystem_dashboard_ticker_status
            WHERE ecosystem_code = ? AND report_date = ? AND run_id = ?
            ORDER BY ticker ASC
            """,
            (run.ecosystem_code, run.report_date, run.run_id),
        ).fetchall()
    )
    return [_row_to_dict(row) for row in rows]


def _load_decision_trace(conn: sqlite3.Connection, run: EcosystemDashboardRunRef) -> list[dict[str, object]]:
    rows = list(
        conn.execute(
            """
            SELECT *
            FROM ecosystem_dashboard_decision_trace
            WHERE ecosystem_code = ? AND run_id = ?
            ORDER BY ticker ASC, trace_index ASC
            """,
            (run.ecosystem_code, run.run_id),
        ).fetchall()
    )
    return [_row_to_dict(row) for row in rows]


def load_dashboard_snapshot(
    dashboard_db: str,
    ecosystem_code: str,
    report_date: str | None = None,
    run_id: str | None = None,
) -> EcosystemDashboardSnapshot:
    run = resolve_dashboard_run(
        dashboard_db=dashboard_db,
        ecosystem_code=ecosystem_code,
        report_date=report_date,
        run_id=run_id,
    )
    with _connect_dashboard_read_only(dashboard_db) as conn:
        return EcosystemDashboardSnapshot(
            run=run,
            source_reports=_load_source_reports(conn, run),
            action_summary=_load_action_summary(conn, run),
            market_map=_load_market_map(conn, run),
            watchlist=_load_watchlist(conn, run),
            tickers=_load_tickers(conn, run),
            decision_trace=_load_decision_trace(conn, run),
        )
