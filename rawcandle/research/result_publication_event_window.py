from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from rawcandle.research.result_publication_daily_ohlc import (
    OhlcDay,
    ResultPublicationResearchDataset,
    ResultPublicationResearchRow,
)


EVENT_WINDOW_VERSION = "result_publication_event_window_v1"
PUBLICATION_RULE_VERSION = "result_publication_daily_research_v1"
PUBLICATION_METADATA_VERSION = "result_publication_research_export_v1"
OFFSETS = (-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 10, 20)
MIN_PRE_EVENT_HISTORY = 15
CORE_DISTRIBUTIONS = (
    "gap_pct",
    "return_D0",
    "return_D5",
    "return_D10",
    "return_D20",
    "relative_return_D5",
    "relative_return_D20",
)


def _offset_name(offset: int) -> str:
    if offset < 0:
        return f"Dm{abs(offset)}"
    if offset > 0:
        return f"Dp{offset}"
    return "D0"


DATE_COLUMNS = tuple(f"date_{_offset_name(offset)}" for offset in OFFSETS)
EVENT_WINDOW_COLUMNS = (
    "company_id",
    "ticker",
    "fiscal_year",
    "fiscal_quarter",
    "research_status",
    "research_confidence",
    "research_method",
    "is_canonical",
    "rule_version",
    "canonical_authority_status",
    "publication_date",
    "publication_session",
    "first_full_post_result_trading_date",
    "warning",
    "D0_date",
    *DATE_COLUMNS,
    "Dm1_close",
    "D0_open",
    "D0_close",
    "Dp1_close",
    "event_window_status",
    "missing_offsets",
    "has_Dm1",
    "has_D0",
    "has_D5",
    "has_D10",
    "has_D20",
    "volume_history_sufficient",
    "spy_available",
    "gap_pct",
    "D0_close_return_pct",
    "D0_intraday_return_pct",
    "D0_range_pct",
    "return_Dm5_to_Dm1",
    "return_Dm3_to_Dm1",
    "return_D0",
    "return_D1",
    "return_D2",
    "return_D3",
    "return_D5",
    "return_D10",
    "return_D20",
    "post_D0_to_D5",
    "post_D0_to_D10",
    "post_D0_to_D20",
    "D0_volume",
    "avg_volume_Dm20_to_Dm1",
    "D0_volume_vs_avg20",
    "avg_range_pct_Dm20_to_Dm1",
    "D0_range_vs_avg20",
    "spy_return_D0",
    "spy_return_D5",
    "spy_return_D10",
    "spy_return_D20",
    "relative_return_D0",
    "relative_return_D5",
    "relative_return_D10",
    "relative_return_D20",
    "D0_abs_close_move_pct",
    "D1_abs_close_move_pct",
    "largest_move_day",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"PUBLICATION_METADATA_INVALID:{path}") from exc
    if not isinstance(value, dict):
        raise ValueError("PUBLICATION_METADATA_INVALID_ROOT")
    return value


def validate_publication_input(
    publication_csv: str | Path, publication_metadata: str | Path
) -> tuple[ResultPublicationResearchDataset, dict[str, Any], str]:
    csv_path = Path(publication_csv).resolve()
    metadata_path = Path(publication_metadata).resolve()
    metadata = _load_json(metadata_path)
    actual_sha = _sha256(csv_path)
    if metadata.get("artifact_version") != PUBLICATION_METADATA_VERSION:
        raise ValueError("PUBLICATION_METADATA_VERSION_INVALID")
    if metadata.get("output_sha256") != actual_sha:
        raise ValueError("PUBLICATION_EXPORT_SHA256_MISMATCH")
    if Path(str(metadata.get("output", ""))).resolve() != csv_path:
        raise ValueError("PUBLICATION_EXPORT_PATH_MISMATCH")
    if metadata.get("projection_rule_version") != PUBLICATION_RULE_VERSION:
        raise ValueError("PUBLICATION_RULE_VERSION_INVALID")
    filters = metadata.get("filters")
    if not isinstance(filters, dict) or filters.get("include_unusable") is not False:
        raise ValueError("PUBLICATION_EXPORT_FILTER_INVALID")

    dataset = ResultPublicationResearchDataset.load(csv_path)
    if metadata.get("exported_rows") != len(dataset):
        raise ValueError("PUBLICATION_EXPORT_ROW_COUNT_MISMATCH")
    status_counts = Counter(row.research_status for row in dataset.rows())
    recorded = metadata.get("status_counts")
    if not isinstance(recorded, dict):
        raise ValueError("PUBLICATION_STATUS_COUNTS_INVALID")
    for status, count in status_counts.items():
        if recorded.get(status) != count:
            raise ValueError(f"PUBLICATION_STATUS_COUNT_MISMATCH:{status}")
    if any(row.rule_version != PUBLICATION_RULE_VERSION for row in dataset.rows()):
        raise ValueError("PUBLICATION_ROW_RULE_VERSION_INVALID")
    return dataset, metadata, actual_sha


def _connect_readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _load_ticker_history(connection: sqlite3.Connection, ticker: str) -> list[OhlcDay]:
    rows = connection.execute(
        "SELECT pvm,open,high,low,close,volume FROM osakedata WHERE osake=? ORDER BY pvm",
        (ticker,),
    ).fetchall()
    return [
        OhlcDay(
            trading_date=str(row["pvm"]),
            open=float(row["open"]) if row["open"] is not None else None,
            high=float(row["high"]) if row["high"] is not None else None,
            low=float(row["low"]) if row["low"] is not None else None,
            close=float(row["close"]) if row["close"] is not None else None,
            volume=int(row["volume"]) if row["volume"] is not None else None,
        )
        for row in rows
    ]


def _pct(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return (numerator / denominator - 1.0) * 100.0


def _average(values: Iterable[float | int | None]) -> float | None:
    usable = [float(value) for value in values if value is not None]
    return sum(usable) / len(usable) if usable else None


def _range_pct(day: OhlcDay | None) -> float | None:
    if day is None:
        return None
    return _pct(day.high, day.low)


def _at(days: Sequence[OhlcDay], index: int, offset: int) -> OhlcDay | None:
    target = index + offset
    return days[target] if 0 <= target < len(days) else None


def _build_event(
    publication: ResultPublicationResearchRow,
    stock_days: Sequence[OhlcDay],
    spy_by_date: Mapping[str, OhlcDay],
) -> dict[str, Any]:
    boundary = publication.first_full_post_result_trading_date
    date_to_index = {day.trading_date: index for index, day in enumerate(stock_days)}
    index = date_to_index.get(boundary) if boundary is not None else None
    observed = {offset: _at(stock_days, index, offset) if index is not None else None for offset in OFFSETS}
    missing = [f"D{offset:+d}" if offset else "D0" for offset in OFFSETS if observed[offset] is None]
    latest = stock_days[-1].trading_date if stock_days else None
    if index is not None:
        status = "COMPLETE" if not missing else "PARTIAL"
    elif boundary is None:
        status = "BOUNDARY_UNAVAILABLE"
    elif boundary is not None and (latest is None or boundary > latest):
        status = "PENDING_D0"
    else:
        status = "MISSING_D0"

    dm1 = observed[-1]
    d0 = observed[0]
    d1 = observed[1]
    metrics: dict[str, Any] = {
        "gap_pct": _pct(d0.open if d0 else None, dm1.close if dm1 else None),
        "D0_close_return_pct": _pct(d0.close if d0 else None, dm1.close if dm1 else None),
        "D0_intraday_return_pct": _pct(d0.close if d0 else None, d0.open if d0 else None),
        "D0_range_pct": _range_pct(d0),
        "return_Dm5_to_Dm1": _pct(
            dm1.close if dm1 else None, observed[-5].close if observed[-5] else None
        ),
        "return_Dm3_to_Dm1": _pct(
            dm1.close if dm1 else None, observed[-3].close if observed[-3] else None
        ),
    }
    for offset in (0, 1, 2, 3, 5, 10, 20):
        day = observed[offset]
        metrics[f"return_D{offset}"] = _pct(
            day.close if day else None, dm1.close if dm1 else None
        )
    for offset in (5, 10, 20):
        day = observed[offset]
        metrics[f"post_D0_to_D{offset}"] = _pct(
            day.close if day else None, d0.close if d0 else None
        )

    pre_days = stock_days[max(0, index - 20) : index] if index is not None else []
    volume_values = [day.volume for day in pre_days if day.volume is not None]
    range_values = [value for value in (_range_pct(day) for day in pre_days) if value is not None]
    sufficient = len(pre_days) >= MIN_PRE_EVENT_HISTORY
    avg_volume = _average(volume_values) if sufficient and len(volume_values) >= MIN_PRE_EVENT_HISTORY else None
    avg_range = _average(range_values) if sufficient and len(range_values) >= MIN_PRE_EVENT_HISTORY else None
    d0_range = metrics["D0_range_pct"]
    metrics.update(
        {
            "D0_volume": d0.volume if d0 else None,
            "avg_volume_Dm20_to_Dm1": avg_volume,
            "D0_volume_vs_avg20": (
                float(d0.volume) / avg_volume if d0 and d0.volume is not None and avg_volume else None
            ),
            "avg_range_pct_Dm20_to_Dm1": avg_range,
            "D0_range_vs_avg20": d0_range / avg_range if d0_range is not None and avg_range else None,
        }
    )

    spy_returns: dict[int, float | None] = {}
    spy_dm1 = spy_by_date.get(dm1.trading_date) if dm1 else None
    for offset in (0, 5, 10, 20):
        stock_day = observed[offset]
        spy_day = spy_by_date.get(stock_day.trading_date) if stock_day else None
        spy_return = _pct(spy_day.close if spy_day else None, spy_dm1.close if spy_dm1 else None)
        spy_returns[offset] = spy_return
        metrics[f"spy_return_D{offset}"] = spy_return
        stock_return = metrics[f"return_D{offset}"]
        metrics[f"relative_return_D{offset}"] = (
            stock_return - spy_return if stock_return is not None and spy_return is not None else None
        )

    d0_abs = abs(metrics["return_D0"]) if metrics["return_D0"] is not None else None
    d1_increment = _pct(d1.close if d1 else None, d0.close if d0 else None)
    d1_abs = abs(d1_increment) if d1_increment is not None else None
    if d0_abs is None or d1_abs is None:
        largest = None
    elif abs(d0_abs - d1_abs) < 1e-12:
        largest = "TIE"
    else:
        largest = "D0" if d0_abs > d1_abs else "D1"

    result: dict[str, Any] = {
        "company_id": publication.key.company_id,
        "ticker": publication.ticker,
        "fiscal_year": publication.key.fiscal_year,
        "fiscal_quarter": publication.key.fiscal_quarter,
        "research_status": publication.research_status,
        "research_confidence": publication.research_confidence,
        "research_method": publication.research_method,
        "is_canonical": publication.is_canonical,
        "rule_version": publication.rule_version,
        "canonical_authority_status": publication.canonical_authority_status,
        "publication_date": publication.research_publication_date,
        "publication_session": publication.research_publication_session,
        "first_full_post_result_trading_date": boundary,
        "warning": publication.warning,
        "D0_date": d0.trading_date if d0 else None,
        "Dm1_close": dm1.close if dm1 else None,
        "D0_open": d0.open if d0 else None,
        "D0_close": d0.close if d0 else None,
        "Dp1_close": d1.close if d1 else None,
        "event_window_status": status,
        "missing_offsets": ",".join(missing),
        "has_Dm1": dm1 is not None,
        "has_D0": d0 is not None,
        "has_D5": observed[5] is not None,
        "has_D10": observed[10] is not None,
        "has_D20": observed[20] is not None,
        "volume_history_sufficient": sufficient,
        "spy_available": all(spy_returns[offset] is not None for offset in (0, 5, 10, 20)),
        **metrics,
        "D0_abs_close_move_pct": d0_abs,
        "D1_abs_close_move_pct": d1_abs,
        "largest_move_day": largest,
    }
    result.update(
        {
            f"date_{_offset_name(offset)}": observed[offset].trading_date if observed[offset] else None
            for offset in OFFSETS
        }
    )
    return result


def build_event_window_rows(
    publications: Sequence[ResultPublicationResearchRow], ohlc_db: str | Path
) -> list[dict[str, Any]]:
    grouped: dict[str, list[ResultPublicationResearchRow]] = defaultdict(list)
    for publication in publications:
        grouped[publication.ticker].append(publication)
    connection = _connect_readonly(Path(ohlc_db))
    try:
        spy_days = _load_ticker_history(connection, "SPY")
        spy_by_date = {day.trading_date: day for day in spy_days}
        results: list[dict[str, Any]] = []
        for ticker in sorted(grouped):
            stock_days = spy_days if ticker == "SPY" else _load_ticker_history(connection, ticker)
            for publication in sorted(grouped[ticker], key=lambda item: item.key):
                results.append(_build_event(publication, stock_days, spy_by_date))
    finally:
        connection.close()
    return sorted(
        results,
        key=lambda row: (int(row["company_id"]), int(row["fiscal_year"]), str(row["fiscal_quarter"])),
    )


def _percentile(values: Sequence[float], percentile: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile / 100.0
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _group_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "event_count": len(rows),
        "complete_D0_count": sum(bool(row["has_D0"]) for row in rows),
        "complete_D5_count": sum(bool(row["has_D5"]) for row in rows),
        "complete_D10_count": sum(bool(row["has_D10"]) for row in rows),
        "complete_D20_count": sum(bool(row["has_D20"]) for row in rows),
    }
    distributions: dict[str, Any] = {}
    for field in CORE_DISTRIBUTIONS:
        values = [float(row[field]) for row in rows if row.get(field) is not None]
        distributions[field] = {
            "count": len(values),
            **{f"p{value}": _percentile(values, value) for value in (10, 25, 50, 75, 90)},
        }
    d5 = [float(row["return_D5"]) for row in rows if row.get("return_D5") is not None]
    result["positive_return_D5_pct"] = (
        sum(value > 0 for value in d5) / len(d5) * 100.0 if d5 else None
    )
    result["distributions"] = distributions
    return result


def summarize_event_windows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[Mapping[str, Any]]] = {"ALL": list(rows)}
    for row in rows:
        groups.setdefault(f"STATUS:{row['research_status']}", []).append(row)
        groups.setdefault(f"IS_CANONICAL:{str(row['is_canonical']).lower()}", []).append(row)
        groups.setdefault(f"METHOD:{row['research_method']}", []).append(row)
    group_summaries = {name: _group_summary(values) for name, values in sorted(groups.items())}
    methods: dict[str, Any] = {}
    for name, values in sorted(groups.items()):
        if not name.startswith("METHOD:"):
            continue
        shift_counts = Counter(str(row.get("largest_move_day") or "UNAVAILABLE") for row in values)
        methods[name.removeprefix("METHOD:")] = {
            "event_count": len(values),
            "small_sample": len(values) < 30,
            "largest_move_day_counts": dict(sorted(shift_counts.items())),
        }
    return {"groups": group_summaries, "method_shift_diagnostic": methods}


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EVENT_WINDOW_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_event_window_dataset(
    publication_csv: str | Path,
    publication_metadata: str | Path,
    ohlc_db: str | Path,
    output_csv: str | Path,
    output_metadata: str | Path,
    *,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    dataset, source_metadata, source_sha = validate_publication_input(
        publication_csv, publication_metadata
    )
    load_seconds = time.perf_counter() - started
    build_started = time.perf_counter()
    rows = build_event_window_rows(dataset.rows(), ohlc_db)
    build_seconds = time.perf_counter() - build_started
    summary_started = time.perf_counter()
    summary = summarize_event_windows(rows)
    summary_seconds = time.perf_counter() - summary_started

    output_path = Path(output_csv)
    _write_csv(output_path, rows)
    method_counts = Counter(str(row["research_method"]) for row in rows)
    status_counts = Counter(str(row["research_status"]) for row in rows)
    counts = {
        "publication_input_rows": len(dataset),
        "joined_D0_rows": sum(bool(row["has_D0"]) for row in rows),
        "missing_D0_rows": sum(not bool(row["has_D0"]) for row in rows),
        "D5_available_rows": sum(bool(row["has_D5"]) for row in rows),
        "D10_available_rows": sum(bool(row["has_D10"]) for row in rows),
        "D20_available_rows": sum(bool(row["has_D20"]) for row in rows),
        "status_counts": dict(sorted(status_counts.items())),
        "method_counts": dict(sorted(method_counts.items())),
    }
    metadata = {
        "artifact_version": EVENT_WINDOW_VERSION,
        "generated_at_utc": generated_at_utc
        or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "publication_rule_version": PUBLICATION_RULE_VERSION,
        "publication_csv": str(Path(publication_csv).resolve()),
        "publication_csv_sha256": source_sha,
        "publication_metadata": str(Path(publication_metadata).resolve()),
        "publication_metadata_sha256": _sha256(Path(publication_metadata)),
        "publication_metadata_output_sha256": source_metadata["output_sha256"],
        "ohlc_db": str(Path(ohlc_db).resolve()),
        "ohlc_db_sha256": _sha256(Path(ohlc_db)),
        "output_csv": str(output_path.resolve()),
        "output_csv_sha256": _sha256(output_path),
        "offsets": list(OFFSETS),
        "minimum_pre_event_history": MIN_PRE_EVENT_HISTORY,
        "counts": counts,
        "summary": summary,
        "performance_seconds": {
            "publication_load_and_preflight": load_seconds,
            "event_window_build": build_seconds,
            "summary": summary_seconds,
        },
    }
    metadata_path = Path(output_metadata)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metadata
