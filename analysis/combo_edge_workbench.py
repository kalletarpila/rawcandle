from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from dataclasses import dataclass
from pathlib import Path
import sqlite3
from statistics import mean

from sklearn.feature_extraction import DictVectorizer
from sklearn.tree import DecisionTreeRegressor
from sklearn.tree import export_text

WORKBENCH_SCHEMA = """
CREATE TABLE IF NOT EXISTS edge_cases (
    case_kind TEXT NOT NULL,
    source_pattern TEXT NOT NULL,
    ticker TEXT NOT NULL,
    finding_date TEXT NOT NULL,
    linked_event_date TEXT NOT NULL,
    pivot2_date_r3 TEXT,
    combo_offset INTEGER,
    pivot_gap_r3 INTEGER,
    pivot_drop_pct_r3 REAL,
    rsi REAL,
    bullish_strength REAL,
    bearish_strength REAL,
    ret_10 REAL,
    ret_20 REAL,
    ret_30 REAL,
    ret_40 REAL,
    winsor_ret_10 REAL,
    winsor_ret_20 REAL,
    winsor_ret_30 REAL,
    winsor_ret_40 REAL,
    PRIMARY KEY (source_pattern, ticker, finding_date)
);

CREATE TABLE IF NOT EXISTS edge_area_summary (
    source_pattern TEXT NOT NULL,
    rsi_scope TEXT NOT NULL,
    gap_bin TEXT NOT NULL,
    drop_bin TEXT NOT NULL,
    n INTEGER NOT NULL,
    win_rate_30 REAL,
    median_ret_30 REAL,
    winsor_ret_10 REAL,
    winsor_ret_20 REAL,
    winsor_ret_30 REAL
);
"""


COMBO_PATTERNS = (
    "BullDiv & Hammer",
    "BullDiv & Piercing Pattern",
    "BullDiv & Bullish Engulfing",
    "BullDiv & Dragonfly Doji",
)
BULLDIV_PATTERN = "Bullish Divergence"
WINSOR_MIN = -50.0
WINSOR_MAX = 50.0


@dataclass(frozen=True)
class DivergenceEvent:
    ticker: str
    event_date: str
    pivot2_date_r3: str | None
    pivot_gap_r3: int | None
    pivot_drop_pct_r3: float | None
    rsi: float | None
    bullish_strength: float | None
    bearish_strength: float | None


@dataclass(frozen=True)
class FindingRow:
    ticker: str
    finding_date: str
    pattern: str


def _winsor(value: float | None) -> float | None:
    if value is None:
        return None
    return max(WINSOR_MIN, min(WINSOR_MAX, value))


def _gap_bin(gap: int | None) -> str:
    if gap is None:
        return "UNKNOWN"
    if 5 <= gap <= 7:
        return "05-07"
    if 8 <= gap <= 10:
        return "08-10"
    if 11 <= gap <= 14:
        return "11-14"
    if 15 <= gap <= 18:
        return "15-18"
    if 19 <= gap <= 22:
        return "19-22"
    if 23 <= gap <= 30:
        return "23-30"
    return "OTHER"


def _drop_bin(drop_value: float | None) -> str:
    if drop_value is None:
        return "UNKNOWN"
    if drop_value < 3.0:
        return "<3"
    if drop_value < 5.0:
        return "3-5"
    if drop_value < 7.0:
        return "5-7"
    return ">7"


def _ensure_workbench_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(WORKBENCH_SCHEMA)
    edge_case_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(edge_cases)").fetchall()
    }
    if "ret_40" not in edge_case_columns:
        conn.execute("ALTER TABLE edge_cases ADD COLUMN ret_40 REAL")
    if "winsor_ret_40" not in edge_case_columns:
        conn.execute("ALTER TABLE edge_cases ADD COLUMN winsor_ret_40 REAL")
    conn.execute("DELETE FROM edge_cases")
    conn.execute("DELETE FROM edge_area_summary")
    conn.commit()


def _load_price_index(stock_db_path: Path) -> tuple[dict[str, dict[str, int]], dict[str, list[float]]]:
    positions: dict[str, dict[str, int]] = {}
    closes: dict[str, list[float]] = {}
    with sqlite3.connect(stock_db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT osake AS ticker, pvm AS date, close
            FROM osakedata
            WHERE close IS NOT NULL
            ORDER BY osake, pvm
            """
        ).fetchall()
    for row in rows:
        ticker = str(row["ticker"])
        positions.setdefault(ticker, {})[str(row["date"])] = len(positions.setdefault(ticker, {}))
        closes.setdefault(ticker, []).append(float(row["close"]))
    return positions, closes


def _load_r3_events(analysis_db_path: Path) -> dict[str, list[DivergenceEvent]]:
    with sqlite3.connect(analysis_db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                ticker,
                date,
                pivot2_date_r3,
                pivot_gap_r3,
                pivot_drop_pct_r3,
                rsi,
                bullish_strength,
                bearish_strength
            FROM divergence_data
            WHERE is_bullish_divergence_r3 = 1
            ORDER BY ticker, date
            """
        ).fetchall()
    by_ticker: dict[str, list[DivergenceEvent]] = {}
    for row in rows:
        event = DivergenceEvent(
            ticker=str(row["ticker"]),
            event_date=str(row["date"]),
            pivot2_date_r3=None if row["pivot2_date_r3"] is None else str(row["pivot2_date_r3"]),
            pivot_gap_r3=None if row["pivot_gap_r3"] is None else int(row["pivot_gap_r3"]),
            pivot_drop_pct_r3=None
            if row["pivot_drop_pct_r3"] is None
            else float(row["pivot_drop_pct_r3"]),
            rsi=None if row["rsi"] is None else float(row["rsi"]),
            bullish_strength=None
            if row["bullish_strength"] is None
            else float(row["bullish_strength"]),
            bearish_strength=None
            if row["bearish_strength"] is None
            else float(row["bearish_strength"]),
        )
        by_ticker.setdefault(event.ticker, []).append(event)
    return by_ticker


def _load_findings(analysis_db_path: Path, patterns: tuple[str, ...]) -> list[FindingRow]:
    placeholders = ",".join("?" for _ in patterns)
    with sqlite3.connect(analysis_db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT ticker, date, pattern
            FROM analysis_findings
            WHERE pattern IN ({placeholders})
            ORDER BY ticker, date, pattern
            """,
            patterns,
        ).fetchall()
    return [
        FindingRow(ticker=str(row["ticker"]), finding_date=str(row["date"]), pattern=str(row["pattern"]))
        for row in rows
    ]


def _calc_return(
    ticker: str,
    start_date: str,
    horizon: int,
    positions: dict[str, dict[str, int]],
    closes: dict[str, list[float]],
) -> float | None:
    ticker_positions = positions.get(ticker)
    if not ticker_positions:
        return None
    start_idx = ticker_positions.get(start_date)
    if start_idx is None:
        return None
    series = closes.get(ticker)
    if not series or start_idx >= len(series):
        return None
    start_close = series[start_idx]
    end_idx = start_idx + horizon
    if start_close == 0 or end_idx >= len(series):
        return None
    return ((series[end_idx] / start_close) - 1.0) * 100.0


def _link_combo_event(
    finding: FindingRow,
    events: list[DivergenceEvent],
    positions: dict[str, dict[str, int]],
) -> tuple[DivergenceEvent, int | None] | None:
    ticker_positions = positions.get(finding.ticker, {})
    combo_pos = ticker_positions.get(finding.finding_date)
    candidates: list[tuple[int, int, str, DivergenceEvent, int | None]] = []
    for event in events:
        event_match = event.event_date == finding.finding_date
        pivot_offset = None
        if combo_pos is not None and event.pivot2_date_r3 is not None:
            pivot_pos = ticker_positions.get(event.pivot2_date_r3)
            if pivot_pos is not None:
                pivot_offset = combo_pos - pivot_pos
        window_match = pivot_offset is not None and -3 <= pivot_offset <= 3
        if not event_match and not window_match:
            continue
        candidates.append(
            (
                0 if event_match else 1,
                abs(pivot_offset) if pivot_offset is not None else 9999,
                event.event_date,
                event,
                pivot_offset,
            )
        )
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    _priority, _distance, _event_date, event, combo_offset = candidates[0]
    return event, combo_offset


def build_workbench(
    *,
    analysis_db_path: Path,
    stock_db_path: Path,
    workbench_db_path: Path,
) -> dict[str, int]:
    positions, closes = _load_price_index(stock_db_path)
    events_by_ticker = _load_r3_events(analysis_db_path)
    findings = _load_findings(analysis_db_path, (BULLDIV_PATTERN, *COMBO_PATTERNS))

    workbench_db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(workbench_db_path) as conn:
        _ensure_workbench_schema(conn)
        inserted = 0
        for finding in findings:
            linked_event: DivergenceEvent | None = None
            combo_offset: int | None = None
            if finding.pattern == BULLDIV_PATTERN:
                linked_event = next(
                    (
                        event
                        for event in events_by_ticker.get(finding.ticker, [])
                        if event.event_date == finding.finding_date
                    ),
                    None,
                )
            else:
                linked = _link_combo_event(
                    finding,
                    events_by_ticker.get(finding.ticker, []),
                    positions,
                )
                if linked is not None:
                    linked_event, combo_offset = linked
            if linked_event is None:
                continue

            ret_10 = _calc_return(finding.ticker, finding.finding_date, 10, positions, closes)
            ret_20 = _calc_return(finding.ticker, finding.finding_date, 20, positions, closes)
            ret_30 = _calc_return(finding.ticker, finding.finding_date, 30, positions, closes)
            ret_40 = _calc_return(finding.ticker, finding.finding_date, 40, positions, closes)

            conn.execute(
                """
                INSERT OR REPLACE INTO edge_cases (
                    case_kind,
                    source_pattern,
                    ticker,
                    finding_date,
                    linked_event_date,
                    pivot2_date_r3,
                    combo_offset,
                    pivot_gap_r3,
                    pivot_drop_pct_r3,
                    rsi,
                    bullish_strength,
                    bearish_strength,
                    ret_10,
                    ret_20,
                    ret_30,
                    ret_40,
                    winsor_ret_10,
                    winsor_ret_20,
                    winsor_ret_30,
                    winsor_ret_40
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "bull_div" if finding.pattern == BULLDIV_PATTERN else "combo",
                    finding.pattern,
                    finding.ticker,
                    finding.finding_date,
                    linked_event.event_date,
                    linked_event.pivot2_date_r3,
                    combo_offset,
                    linked_event.pivot_gap_r3,
                    linked_event.pivot_drop_pct_r3,
                    linked_event.rsi,
                    linked_event.bullish_strength,
                    linked_event.bearish_strength,
                    ret_10,
                    ret_20,
                    ret_30,
                    ret_40,
                    _winsor(ret_10),
                    _winsor(ret_20),
                    _winsor(ret_30),
                    _winsor(ret_40),
                ),
            )
            inserted += 1
        conn.commit()
    return {"inserted_rows": inserted, "source_findings": len(findings)}


def _write_area_summary(workbench_db_path: Path, output_csv_path: Path) -> int:
    with sqlite3.connect(workbench_db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                source_pattern,
                CASE
                    WHEN rsi < 36 THEN 'LT_36'
                    ELSE 'ALL'
                END AS row_scope,
                pivot_gap_r3,
                pivot_drop_pct_r3,
                winsor_ret_10,
                winsor_ret_20,
                winsor_ret_30,
                ret_30
            FROM edge_cases
            WHERE pivot_gap_r3 IS NOT NULL
              AND pivot_drop_pct_r3 IS NOT NULL
              AND winsor_ret_30 IS NOT NULL
            """
        ).fetchall()

        grouped: dict[tuple[str, str, str, str], list[sqlite3.Row]] = defaultdict(list)
        for row in rows:
            source_pattern = str(row["source_pattern"])
            gap_bin = _gap_bin(int(row["pivot_gap_r3"]))
            drop_bin = _drop_bin(float(row["pivot_drop_pct_r3"]))
            grouped[(source_pattern, "ALL", gap_bin, drop_bin)].append(row)
            if str(row["row_scope"]) == "LT_36":
                grouped[(source_pattern, "LT_36", gap_bin, drop_bin)].append(row)

        summary_rows: list[dict[str, object]] = []
        for (source_pattern, rsi_scope, gap_bin, drop_bin), group_rows in sorted(grouped.items()):
            ret30_values = [float(row["ret_30"]) for row in group_rows if row["ret_30"] is not None]
            winsor10 = [float(row["winsor_ret_10"]) for row in group_rows if row["winsor_ret_10"] is not None]
            winsor20 = [float(row["winsor_ret_20"]) for row in group_rows if row["winsor_ret_20"] is not None]
            winsor30 = [float(row["winsor_ret_30"]) for row in group_rows if row["winsor_ret_30"] is not None]
            if not winsor30:
                continue
            n = len(winsor30)
            win_rate_30 = None
            median_ret_30 = None
            if ret30_values:
                positives = sum(1 for value in ret30_values if value > 0)
                win_rate_30 = (positives / len(ret30_values)) * 100.0
                sorted_ret30 = sorted(ret30_values)
                mid = len(sorted_ret30) // 2
                if len(sorted_ret30) % 2 == 1:
                    median_ret_30 = sorted_ret30[mid]
                else:
                    median_ret_30 = (sorted_ret30[mid - 1] + sorted_ret30[mid]) / 2.0
            summary_rows.append(
                {
                    "source_pattern": source_pattern,
                    "rsi_scope": rsi_scope,
                    "gap_bin": gap_bin,
                    "drop_bin": drop_bin,
                    "n": n,
                    "win_rate_30": win_rate_30,
                    "median_ret_30": median_ret_30,
                    "winsor_ret_10": mean(winsor10) if winsor10 else None,
                    "winsor_ret_20": mean(winsor20) if winsor20 else None,
                    "winsor_ret_30": mean(winsor30) if winsor30 else None,
                }
            )

        conn.execute("DELETE FROM edge_area_summary")
        conn.executemany(
            """
            INSERT INTO edge_area_summary (
                source_pattern,
                rsi_scope,
                gap_bin,
                drop_bin,
                n,
                win_rate_30,
                median_ret_30,
                winsor_ret_10,
                winsor_ret_20,
                winsor_ret_30
            ) VALUES (
                :source_pattern,
                :rsi_scope,
                :gap_bin,
                :drop_bin,
                :n,
                :win_rate_30,
                :median_ret_30,
                :winsor_ret_10,
                :winsor_ret_20,
                :winsor_ret_30
            )
            """,
            summary_rows,
        )
        conn.commit()

    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with output_csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "source_pattern",
                "rsi_scope",
                "gap_bin",
                "drop_bin",
                "n",
                "win_rate_30",
                "median_ret_30",
                "winsor_ret_10",
                "winsor_ret_20",
                "winsor_ret_30",
            ],
        )
        writer.writeheader()
        writer.writerows(summary_rows)
    return len(summary_rows)


def _write_tree_report(workbench_db_path: Path, output_path: Path) -> None:
    with sqlite3.connect(workbench_db_path) as conn:
        conn.row_factory = sqlite3.Row
        all_rows = conn.execute(
            """
            SELECT source_pattern, pivot_gap_r3, pivot_drop_pct_r3, rsi, combo_offset, winsor_ret_30
            FROM edge_cases
            WHERE winsor_ret_30 IS NOT NULL
              AND pivot_gap_r3 IS NOT NULL
              AND pivot_drop_pct_r3 IS NOT NULL
            """
        ).fetchall()
        combo_rows = conn.execute(
            """
            SELECT source_pattern, pivot_gap_r3, pivot_drop_pct_r3, rsi, combo_offset, winsor_ret_30
            FROM edge_cases
            WHERE case_kind = 'combo'
              AND winsor_ret_30 IS NOT NULL
              AND pivot_gap_r3 IS NOT NULL
              AND pivot_drop_pct_r3 IS NOT NULL
            """
        ).fetchall()

    def fit_report(rows: list[sqlite3.Row], title: str, min_leaf: int) -> str:
        if len(rows) < max(20, min_leaf * 2):
            return f"{title}\nNot enough rows for tree model.\n"
        feature_rows = []
        targets = []
        for row in rows:
            feature_rows.append(
                {
                    "source_pattern": str(row["source_pattern"]),
                    "pivot_gap_r3": float(row["pivot_gap_r3"]),
                    "pivot_drop_pct_r3": float(row["pivot_drop_pct_r3"]),
                    "rsi": float(row["rsi"]) if row["rsi"] is not None else 999.0,
                    "combo_offset": float(row["combo_offset"])
                    if row["combo_offset"] is not None
                    else 99.0,
                }
            )
            targets.append(float(row["winsor_ret_30"]))
        vectorizer = DictVectorizer(sparse=False)
        matrix = vectorizer.fit_transform(feature_rows)
        model = DecisionTreeRegressor(max_depth=3, min_samples_leaf=min_leaf, random_state=42)
        model.fit(matrix, targets)
        return (
            f"{title}\n"
            f"rows={len(rows)}\n"
            f"{export_text(model, feature_names=list(vectorizer.get_feature_names_out()))}\n"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        fit_report(all_rows, "All BullDiv + Combo Cases", 50)
        + "\n"
        + fit_report(combo_rows, "Combo Cases Only", 20),
        encoding="utf-8",
    )


def run_pipeline(
    *,
    analysis_db_path: Path,
    stock_db_path: Path,
    workbench_db_path: Path,
    area_summary_csv_path: Path,
    tree_report_path: Path,
) -> dict[str, int]:
    stats = build_workbench(
        analysis_db_path=analysis_db_path,
        stock_db_path=stock_db_path,
        workbench_db_path=workbench_db_path,
    )
    summary_rows = _write_area_summary(workbench_db_path, area_summary_csv_path)
    _write_tree_report(workbench_db_path, tree_report_path)
    return {**stats, "summary_rows": summary_rows}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a persistent combo/BullDiv edge-analysis workbench database and reports."
    )
    parser.add_argument(
        "--analysis-db",
        default="data/analysis.db",
        help="Path to analysis SQLite database.",
    )
    parser.add_argument(
        "--stock-db",
        default="data/osakedata.db",
        help="Path to stock price SQLite database.",
    )
    parser.add_argument(
        "--workbench-db",
        default="data/combo_edge_workbench.db",
        help="Path to persistent workbench SQLite database.",
    )
    parser.add_argument(
        "--area-summary-csv",
        default="reports/combo_edge_area_summary.csv",
        help="Path to area summary CSV output.",
    )
    parser.add_argument(
        "--tree-report",
        default="reports/combo_edge_tree_rules.txt",
        help="Path to tree rules text report.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    stats = run_pipeline(
        analysis_db_path=Path(args.analysis_db),
        stock_db_path=Path(args.stock_db),
        workbench_db_path=Path(args.workbench_db),
        area_summary_csv_path=Path(args.area_summary_csv),
        tree_report_path=Path(args.tree_report),
    )
    print(f"workbench_db={Path(args.workbench_db)}")
    print(f"area_summary_csv={Path(args.area_summary_csv)}")
    print(f"tree_report={Path(args.tree_report)}")
    print(f"source_findings={stats['source_findings']}")
    print(f"inserted_rows={stats['inserted_rows']}")
    print(f"summary_rows={stats['summary_rows']}")


if __name__ == "__main__":
    main()
