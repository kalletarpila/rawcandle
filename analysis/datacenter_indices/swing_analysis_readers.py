from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date


DOW_STATUS_OK = "OK"
DOW_STATUS_NO_DOW_EVENT = "NO_DOW_EVENT"
DOW_STATUS_MISSING_TABLE = "MISSING_TABLE"

DIVERGENCE_STATUS_OK = "OK"
DIVERGENCE_STATUS_NO_DIVERGENCE_ROW = "NO_DIVERGENCE_ROW"
DIVERGENCE_STATUS_MISSING_TABLE = "MISSING_TABLE"

CANDLE_STATUS_OK = "OK"
CANDLE_STATUS_NO_CANDLE_FINDING = "NO_CANDLE_FINDING"
CANDLE_STATUS_MISSING_TABLE = "MISSING_TABLE"

VALID_DOW_STRUCTURE_LABELS = frozenset({"HH", "HL", "LH", "LL"})


BULLISH_PATTERN_NAMES = frozenset(
    {
        "Hammer",
        "Bullish Engulfing",
        "Piercing Pattern",
        "Three White Soldiers",
        "Morning Star",
        "Dragonfly Doji",
        "Bullish Abandoned Baby",
        "Bullish Flag",
        "Bull Rectangle",
        "Ascending Triangle",
        "Bullish Pennant",
        "Cup and Handle",
    }
)

BEARISH_PATTERN_NAMES = frozenset(
    {
        "Bearish Engulfing",
        "Shooting Star",
        "Dark Cloud Cover",
        "Evening Star",
        "Hanging Man",
        "Bearish Flag",
        "Bear Rectangle",
        "Descending Triangle",
        "Bearish Pennant",
        "Falling Three Methods",
    }
)


@dataclass(frozen=True)
class DowStructureEnrichmentSnapshot:
    ticker: str
    market: str | None
    as_of_date: str
    latest_structure_label: str | None
    latest_structure_confirmed_as_of_date: str | None
    latest_event_date: str | None
    trend_state: str | None
    source_status: str


@dataclass(frozen=True)
class DivergenceEnrichmentSnapshot:
    ticker: str
    as_of_date: str
    source_date: str | None
    bullish_divergence_signal: int | None
    bearish_divergence_signal: int | None
    hidden_bullish_divergence_signal: int | None
    hidden_bearish_divergence_signal: int | None
    bullish_strength: float | None
    bearish_strength: float | None
    hidden_bullish_strength: float | None
    hidden_bearish_strength: float | None
    rsi: float | None
    source_status: str


@dataclass(frozen=True)
class CandlestickEnrichmentSnapshot:
    ticker: str
    as_of_date: str
    source_date: str | None
    bullish_candle_signal: int | None
    bearish_candle_signal: int | None
    bullish_patterns: tuple[str, ...]
    bearish_patterns: tuple[str, ...]
    source_status: str


@dataclass(frozen=True)
class TickerAnalysisEnrichmentSnapshot:
    dow: DowStructureEnrichmentSnapshot
    divergence: DivergenceEnrichmentSnapshot
    candlestick: CandlestickEnrichmentSnapshot


def _chunked_values(values: list[str], chunk_size: int = 900) -> list[list[str]]:
    return [values[index:index + chunk_size] for index in range(0, len(values), chunk_size)]


def _parse_iso_date(value: str, field_name: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name}: {value}") from exc


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _resolve_label(row: sqlite3.Row) -> str | None:
    label_high = row["dow_label_high"]
    label_low = row["dow_label_low"]
    event_type = row["event_type"]
    if label_high and label_low:
        if event_type == "PIVOT_HIGH":
            label = str(label_high)
            return label if label in VALID_DOW_STRUCTURE_LABELS else None
        if event_type == "PIVOT_LOW":
            label = str(label_low)
            return label if label in VALID_DOW_STRUCTURE_LABELS else None
        label = str(label_high)
        return label if label in VALID_DOW_STRUCTURE_LABELS else None
    if label_high:
        label = str(label_high)
        return label if label in VALID_DOW_STRUCTURE_LABELS else None
    if label_low:
        label = str(label_low)
        return label if label in VALID_DOW_STRUCTURE_LABELS else None
    return None


def read_dow_structure_enrichment(
    conn: sqlite3.Connection,
    ticker: str,
    market: str | None,
    as_of_date: str,
) -> DowStructureEnrichmentSnapshot:
    normalized_as_of_date = _parse_iso_date(as_of_date, "as_of_date")
    if not _table_exists(conn, "stock_dow_structure_events"):
        return DowStructureEnrichmentSnapshot(
            ticker=ticker,
            market=market,
            as_of_date=normalized_as_of_date,
            latest_structure_label=None,
            latest_structure_confirmed_as_of_date=None,
            latest_event_date=None,
            trend_state=None,
            source_status=DOW_STATUS_MISSING_TABLE,
        )

    params: list[object] = [ticker, normalized_as_of_date]
    market_sql = ""
    if market is not None:
        market_sql = " AND (market = ? OR market IS NULL)"
        params.append(market)

    row = conn.execute(
        f"""
        SELECT
            id,
            ticker,
            market,
            event_date,
            confirmed_as_of_date,
            event_type,
            dow_label_high,
            dow_label_low,
            trend_state
        FROM stock_dow_structure_events
        WHERE ticker = ?
          AND confirmed_as_of_date <= ?
          AND (
                dow_label_high IN ('HH', 'HL', 'LH', 'LL')
                OR dow_label_low IN ('HH', 'HL', 'LH', 'LL')
          )
          {market_sql}
        ORDER BY confirmed_as_of_date DESC, event_date DESC, id DESC
        LIMIT 1
        """,
        params,
    ).fetchone()

    if row is None:
        return DowStructureEnrichmentSnapshot(
            ticker=ticker,
            market=market,
            as_of_date=normalized_as_of_date,
            latest_structure_label=None,
            latest_structure_confirmed_as_of_date=None,
            latest_event_date=None,
            trend_state=None,
            source_status=DOW_STATUS_NO_DOW_EVENT,
        )

    return DowStructureEnrichmentSnapshot(
        ticker=str(row["ticker"]),
        market=market if market is not None else row["market"],
        as_of_date=normalized_as_of_date,
        latest_structure_label=_resolve_label(row),
        latest_structure_confirmed_as_of_date=str(row["confirmed_as_of_date"]),
        latest_event_date=str(row["event_date"]),
        trend_state=None if row["trend_state"] is None else str(row["trend_state"]),
        source_status=DOW_STATUS_OK,
    )


def read_divergence_enrichment(
    conn: sqlite3.Connection,
    ticker: str,
    as_of_date: str,
) -> DivergenceEnrichmentSnapshot:
    normalized_as_of_date = _parse_iso_date(as_of_date, "as_of_date")
    if not _table_exists(conn, "divergence_data"):
        return DivergenceEnrichmentSnapshot(
            ticker=ticker,
            as_of_date=normalized_as_of_date,
            source_date=None,
            bullish_divergence_signal=None,
            bearish_divergence_signal=None,
            hidden_bullish_divergence_signal=None,
            hidden_bearish_divergence_signal=None,
            bullish_strength=None,
            bearish_strength=None,
            hidden_bullish_strength=None,
            hidden_bearish_strength=None,
            rsi=None,
            source_status=DIVERGENCE_STATUS_MISSING_TABLE,
        )

    row = conn.execute(
        """
        SELECT
            ticker,
            date,
            bullish_strength,
            bearish_strength,
            hidden_bullish_strength,
            hidden_bearish_strength,
            rsi,
            is_bullish_divergence_r3,
            is_bearish_divergence_r3,
            is_hidden_bullish_divergence_r3,
            is_hidden_bearish_divergence_r3
        FROM divergence_data
        WHERE ticker = ?
          AND date <= ?
        ORDER BY date DESC
        LIMIT 1
        """,
        (ticker, normalized_as_of_date),
    ).fetchone()

    if row is None:
        return DivergenceEnrichmentSnapshot(
            ticker=ticker,
            as_of_date=normalized_as_of_date,
            source_date=None,
            bullish_divergence_signal=None,
            bearish_divergence_signal=None,
            hidden_bullish_divergence_signal=None,
            hidden_bearish_divergence_signal=None,
            bullish_strength=None,
            bearish_strength=None,
            hidden_bullish_strength=None,
            hidden_bearish_strength=None,
            rsi=None,
            source_status=DIVERGENCE_STATUS_NO_DIVERGENCE_ROW,
        )

    return DivergenceEnrichmentSnapshot(
        ticker=str(row["ticker"]),
        as_of_date=normalized_as_of_date,
        source_date=str(row["date"]),
        bullish_divergence_signal=int(row["is_bullish_divergence_r3"] or 0),
        bearish_divergence_signal=int(row["is_bearish_divergence_r3"] or 0),
        hidden_bullish_divergence_signal=int(row["is_hidden_bullish_divergence_r3"] or 0),
        hidden_bearish_divergence_signal=int(row["is_hidden_bearish_divergence_r3"] or 0),
        bullish_strength=None if row["bullish_strength"] is None else float(row["bullish_strength"]),
        bearish_strength=None if row["bearish_strength"] is None else float(row["bearish_strength"]),
        hidden_bullish_strength=None if row["hidden_bullish_strength"] is None else float(row["hidden_bullish_strength"]),
        hidden_bearish_strength=None if row["hidden_bearish_strength"] is None else float(row["hidden_bearish_strength"]),
        rsi=None if row["rsi"] is None else float(row["rsi"]),
        source_status=DIVERGENCE_STATUS_OK,
    )


def read_candlestick_enrichment(
    conn: sqlite3.Connection,
    ticker: str,
    as_of_date: str,
) -> CandlestickEnrichmentSnapshot:
    normalized_as_of_date = _parse_iso_date(as_of_date, "as_of_date")
    if not _table_exists(conn, "analysis_findings"):
        return CandlestickEnrichmentSnapshot(
            ticker=ticker,
            as_of_date=normalized_as_of_date,
            source_date=None,
            bullish_candle_signal=None,
            bearish_candle_signal=None,
            bullish_patterns=(),
            bearish_patterns=(),
            source_status=CANDLE_STATUS_MISSING_TABLE,
        )

    rows = conn.execute(
        """
        SELECT ticker, date, pattern
        FROM analysis_findings
        WHERE ticker = ?
          AND date = ?
        ORDER BY pattern ASC, id ASC
        """,
        (ticker, normalized_as_of_date),
    ).fetchall()

    if not rows:
        return CandlestickEnrichmentSnapshot(
            ticker=ticker,
            as_of_date=normalized_as_of_date,
            source_date=None,
            bullish_candle_signal=0,
            bearish_candle_signal=0,
            bullish_patterns=(),
            bearish_patterns=(),
            source_status=CANDLE_STATUS_NO_CANDLE_FINDING,
        )

    bullish_patterns = tuple(
        pattern
        for pattern in (str(row["pattern"]) for row in rows if row["pattern"] is not None)
        if pattern in BULLISH_PATTERN_NAMES
    )
    bearish_patterns = tuple(
        pattern
        for pattern in (str(row["pattern"]) for row in rows if row["pattern"] is not None)
        if pattern in BEARISH_PATTERN_NAMES
    )

    return CandlestickEnrichmentSnapshot(
        ticker=ticker,
        as_of_date=normalized_as_of_date,
        source_date=normalized_as_of_date,
        bullish_candle_signal=int(bool(bullish_patterns)),
        bearish_candle_signal=int(bool(bearish_patterns)),
        bullish_patterns=tuple(sorted(set(bullish_patterns))),
        bearish_patterns=tuple(sorted(set(bearish_patterns))),
        source_status=CANDLE_STATUS_OK,
    )


def read_ticker_analysis_enrichment(
    conn: sqlite3.Connection,
    ticker: str,
    market: str | None,
    as_of_date: str,
) -> TickerAnalysisEnrichmentSnapshot:
    return TickerAnalysisEnrichmentSnapshot(
        dow=read_dow_structure_enrichment(conn, ticker, market, as_of_date),
        divergence=read_divergence_enrichment(conn, ticker, as_of_date),
        candlestick=read_candlestick_enrichment(conn, ticker, as_of_date),
    )


def read_batch_dow_structure_enrichment(
    conn: sqlite3.Connection,
    tickers: list[str],
    market: str | None,
    as_of_date: str,
) -> dict[str, DowStructureEnrichmentSnapshot]:
    normalized_as_of_date = _parse_iso_date(as_of_date, "as_of_date")
    has_table = _table_exists(conn, "stock_dow_structure_events")
    snapshots = {
        ticker: DowStructureEnrichmentSnapshot(
            ticker=ticker,
            market=market,
            as_of_date=normalized_as_of_date,
            latest_structure_label=None,
            latest_structure_confirmed_as_of_date=None,
            latest_event_date=None,
            trend_state=None,
            source_status=DOW_STATUS_MISSING_TABLE if not has_table else DOW_STATUS_NO_DOW_EVENT,
        )
        for ticker in tickers
    }
    if not tickers or not has_table:
        return snapshots

    market_sql = ""
    market_params: list[object] = []
    if market is not None:
        market_sql = " AND (market = ? OR market IS NULL)"
        market_params.append(market)

    selected_rows: dict[str, sqlite3.Row] = {}
    for chunk in _chunked_values(tickers):
        placeholders = ", ".join("?" for _ in chunk)
        params: list[object] = [*chunk, normalized_as_of_date, *market_params]
        rows = conn.execute(
            f"""
            SELECT
                id,
                ticker,
                market,
                event_date,
                confirmed_as_of_date,
                event_type,
                dow_label_high,
                dow_label_low,
                trend_state
            FROM stock_dow_structure_events
            WHERE ticker IN ({placeholders})
              AND confirmed_as_of_date <= ?
              AND (
                    dow_label_high IN ('HH', 'HL', 'LH', 'LL')
                    OR dow_label_low IN ('HH', 'HL', 'LH', 'LL')
              )
              {market_sql}
            ORDER BY ticker ASC, confirmed_as_of_date DESC, event_date DESC, id DESC
            """,
            params,
        ).fetchall()
        for row in rows:
            ticker = str(row["ticker"])
            if ticker not in selected_rows:
                selected_rows[ticker] = row

    for ticker, row in selected_rows.items():
        snapshots[ticker] = DowStructureEnrichmentSnapshot(
            ticker=ticker,
            market=market if market is not None else row["market"],
            as_of_date=normalized_as_of_date,
            latest_structure_label=_resolve_label(row),
            latest_structure_confirmed_as_of_date=str(row["confirmed_as_of_date"]),
            latest_event_date=str(row["event_date"]),
            trend_state=None if row["trend_state"] is None else str(row["trend_state"]),
            source_status=DOW_STATUS_OK,
        )
    return snapshots


def read_batch_divergence_enrichment(
    conn: sqlite3.Connection,
    tickers: list[str],
    as_of_date: str,
) -> dict[str, DivergenceEnrichmentSnapshot]:
    normalized_as_of_date = _parse_iso_date(as_of_date, "as_of_date")
    has_table = _table_exists(conn, "divergence_data")
    snapshots = {
        ticker: DivergenceEnrichmentSnapshot(
            ticker=ticker,
            as_of_date=normalized_as_of_date,
            source_date=None,
            bullish_divergence_signal=None,
            bearish_divergence_signal=None,
            hidden_bullish_divergence_signal=None,
            hidden_bearish_divergence_signal=None,
            bullish_strength=None,
            bearish_strength=None,
            hidden_bullish_strength=None,
            hidden_bearish_strength=None,
            rsi=None,
            source_status=DIVERGENCE_STATUS_MISSING_TABLE if not has_table else DIVERGENCE_STATUS_NO_DIVERGENCE_ROW,
        )
        for ticker in tickers
    }
    if not tickers or not has_table:
        return snapshots

    selected_rows: dict[str, sqlite3.Row] = {}
    for chunk in _chunked_values(tickers):
        placeholders = ", ".join("?" for _ in chunk)
        rows = conn.execute(
            f"""
            SELECT
                ticker,
                date,
                bullish_strength,
                bearish_strength,
                hidden_bullish_strength,
                hidden_bearish_strength,
                rsi,
                is_bullish_divergence_r3,
                is_bearish_divergence_r3,
                is_hidden_bullish_divergence_r3,
                is_hidden_bearish_divergence_r3
            FROM divergence_data
            WHERE ticker IN ({placeholders})
              AND date <= ?
            ORDER BY ticker ASC, date DESC
            """,
            [*chunk, normalized_as_of_date],
        ).fetchall()
        for row in rows:
            ticker = str(row["ticker"])
            if ticker not in selected_rows:
                selected_rows[ticker] = row

    for ticker, row in selected_rows.items():
        snapshots[ticker] = DivergenceEnrichmentSnapshot(
            ticker=ticker,
            as_of_date=normalized_as_of_date,
            source_date=str(row["date"]),
            bullish_divergence_signal=int(row["is_bullish_divergence_r3"] or 0),
            bearish_divergence_signal=int(row["is_bearish_divergence_r3"] or 0),
            hidden_bullish_divergence_signal=int(row["is_hidden_bullish_divergence_r3"] or 0),
            hidden_bearish_divergence_signal=int(row["is_hidden_bearish_divergence_r3"] or 0),
            bullish_strength=None if row["bullish_strength"] is None else float(row["bullish_strength"]),
            bearish_strength=None if row["bearish_strength"] is None else float(row["bearish_strength"]),
            hidden_bullish_strength=None if row["hidden_bullish_strength"] is None else float(row["hidden_bullish_strength"]),
            hidden_bearish_strength=None if row["hidden_bearish_strength"] is None else float(row["hidden_bearish_strength"]),
            rsi=None if row["rsi"] is None else float(row["rsi"]),
            source_status=DIVERGENCE_STATUS_OK,
        )
    return snapshots


def read_batch_candlestick_enrichment(
    conn: sqlite3.Connection,
    tickers: list[str],
    as_of_date: str,
) -> dict[str, CandlestickEnrichmentSnapshot]:
    normalized_as_of_date = _parse_iso_date(as_of_date, "as_of_date")
    has_table = _table_exists(conn, "analysis_findings")
    snapshots = {
        ticker: CandlestickEnrichmentSnapshot(
            ticker=ticker,
            as_of_date=normalized_as_of_date,
            source_date=None,
            bullish_candle_signal=None,
            bearish_candle_signal=None,
            bullish_patterns=(),
            bearish_patterns=(),
            source_status=CANDLE_STATUS_MISSING_TABLE if not has_table else CANDLE_STATUS_NO_CANDLE_FINDING,
        )
        for ticker in tickers
    }
    if not tickers or not has_table:
        return snapshots

    grouped_patterns: dict[str, list[str]] = {ticker: [] for ticker in tickers}
    for chunk in _chunked_values(tickers):
        placeholders = ", ".join("?" for _ in chunk)
        rows = conn.execute(
            f"""
            SELECT ticker, date, pattern
            FROM analysis_findings
            WHERE ticker IN ({placeholders})
              AND date = ?
            ORDER BY ticker ASC, pattern ASC, id ASC
            """,
            [*chunk, normalized_as_of_date],
        ).fetchall()
        for row in rows:
            if row["pattern"] is not None:
                grouped_patterns[str(row["ticker"])].append(str(row["pattern"]))

    for ticker, patterns in grouped_patterns.items():
        if not patterns:
            snapshots[ticker] = CandlestickEnrichmentSnapshot(
                ticker=ticker,
                as_of_date=normalized_as_of_date,
                source_date=None,
                bullish_candle_signal=0,
                bearish_candle_signal=0,
                bullish_patterns=(),
                bearish_patterns=(),
                source_status=CANDLE_STATUS_NO_CANDLE_FINDING,
            )
            continue
        bullish_patterns = tuple(sorted({pattern for pattern in patterns if pattern in BULLISH_PATTERN_NAMES}))
        bearish_patterns = tuple(sorted({pattern for pattern in patterns if pattern in BEARISH_PATTERN_NAMES}))
        snapshots[ticker] = CandlestickEnrichmentSnapshot(
            ticker=ticker,
            as_of_date=normalized_as_of_date,
            source_date=normalized_as_of_date,
            bullish_candle_signal=int(bool(bullish_patterns)),
            bearish_candle_signal=int(bool(bearish_patterns)),
            bullish_patterns=bullish_patterns,
            bearish_patterns=bearish_patterns,
            source_status=CANDLE_STATUS_OK,
        )
    return snapshots


def read_batch_ticker_analysis_enrichment(
    conn: sqlite3.Connection,
    tickers: list[str],
    market: str | None,
    as_of_date: str,
) -> dict[str, TickerAnalysisEnrichmentSnapshot]:
    dow_snapshots = read_batch_dow_structure_enrichment(conn, tickers, market, as_of_date)
    divergence_snapshots = read_batch_divergence_enrichment(conn, tickers, as_of_date)
    candle_snapshots = read_batch_candlestick_enrichment(conn, tickers, as_of_date)
    return {
        ticker: TickerAnalysisEnrichmentSnapshot(
            dow=dow_snapshots[ticker],
            divergence=divergence_snapshots[ticker],
            candlestick=candle_snapshots[ticker],
        )
        for ticker in tickers
    }
