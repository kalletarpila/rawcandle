import sqlite3

from rawcandle.cli.export_technical_signal_relevance import main
from rawcandle.technical_signal_relevance import TechnicalSignalRelevanceConfig
from rawcandle.technical_signal_relevance_persistence import (
    TechnicalSignalRelevanceStoredRow,
    apply_technical_signal_relevance_migration,
    build_relevance_run_row,
    insert_relevance_records,
    insert_relevance_run,
)


def _connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    apply_technical_signal_relevance_migration(conn)
    return conn


def _db_path(tmp_path):
    return tmp_path / "analysis_export_cli.db"


def _insert_run(conn: sqlite3.Connection, run_id: str) -> None:
    insert_relevance_run(
        conn,
        build_relevance_run_row(
            run_id=run_id,
            config=TechnicalSignalRelevanceConfig(),
            created_at_utc="2026-05-22T00:00:00Z",
        ),
    )


def _insert_record(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ticker: str,
    signal_date: str,
    signal_name: str,
    relevance_class: str,
    relevance_reason: str,
    rule_trace: str | None = None,
) -> None:
    insert_relevance_records(
        conn,
        [
            TechnicalSignalRelevanceStoredRow(
                ticker=ticker,
                timeframe="1d",
                signal_date=signal_date,
                signal_confirmed_as_of_date=signal_date,
                signal_name=signal_name,
                signal_close_price=100.0,
                signal_direction="BULLISH",
                signal_family="REVERSAL_MEDIUM",
                signal_source_type="CANDLE",
                signal_source_id="CANDLE",
                dow_trend_state="UP",
                dow_context_state="NORMAL",
                latest_bos_direction="BOS_UP",
                bars_since_latest_bos=3,
                latest_reset_reason="RESET",
                bars_since_latest_reset=8,
                near_latest_pivot=1,
                near_active_bos_level=0,
                is_trend_aligned=1,
                is_counter_trend=0,
                relevance_class=relevance_class,
                relevance_reason=relevance_reason,
                relevance_rule_version="TECH_SIGNAL_RELEVANCE_V1",
                mapping_version="TECH_SIGNAL_MAPPING_V1",
                reason_version="TECH_SIGNAL_RELEVANCE_REASON_V1",
                rule_trace=rule_trace,
                created_at_utc="2026-05-22T00:00:00Z",
                run_id=run_id,
            )
        ],
    )


def _table_count(conn: sqlite3.Connection, table_name: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])


def _summary(output: str) -> dict[str, str]:
    summary = {}
    for line in output.splitlines():
        if line.startswith("SUMMARY "):
            key, value = line[len("SUMMARY ") :].split("=", 1)
            summary[key] = value
    return summary


def test_export_cli_returns_one_persisted_relevance_row(tmp_path, capsys):
    db_path = _db_path(tmp_path)
    conn = _connect(db_path)
    _insert_run(conn, "RUN_A")
    _insert_record(
        conn,
        run_id="RUN_A",
        ticker="AAA",
        signal_date="2026-05-01",
        signal_name="Hammer",
        relevance_class="RELEVANT",
        relevance_reason="UP_TREND_BULLISH_DIP_REVERSAL_NEAR_PIVOT_LOW",
    )
    conn.commit()
    conn.close()

    result = main(["--analysis-db", str(db_path), "--run-id", "RUN_A"])

    output = capsys.readouterr().out
    assert result == 0
    assert "technical_signal_relevance_export;RUN_A;AAA;1d;2026-05-01;2026-05-01;Hammer;CANDLE;RELEVANT;" in output


def test_export_cli_output_includes_exact_section_line_and_header(tmp_path, capsys):
    db_path = _db_path(tmp_path)
    conn = _connect(db_path)
    _insert_run(conn, "RUN_A")
    conn.commit()
    conn.close()

    main(["--analysis-db", str(db_path), "--run-id", "RUN_A"])

    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "section;technical_signal_relevance_export"
    assert lines[1] == (
        "section;run_id;ticker;timeframe;signal_date;signal_confirmed_as_of_date;"
        "signal_name;signal_source_id;relevance_class;relevance_reason;dow_trend_state;"
        "dow_context_state;latest_bos_direction;bars_since_latest_bos;"
        "bars_since_latest_reset;near_latest_pivot;near_active_bos_level;"
        "is_trend_aligned;is_counter_trend"
    )


def test_export_cli_is_semicolon_separated_and_deterministic(tmp_path, capsys):
    db_path = _db_path(tmp_path)
    conn = _connect(db_path)
    _insert_run(conn, "RUN_B")
    _insert_record(conn, run_id="RUN_B", ticker="BBB", signal_date="2026-05-02", signal_name="Hammer", relevance_class="WEAK_CONTEXT", relevance_reason="A")
    _insert_record(conn, run_id="RUN_B", ticker="AAA", signal_date="2026-05-01", signal_name="Bearish Divergence", relevance_class="NOISE", relevance_reason="B")
    conn.commit()
    conn.close()

    main(["--analysis-db", str(db_path), "--run-id", "RUN_B"])

    lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith("technical_signal_relevance_export;")]
    assert lines == [
        "technical_signal_relevance_export;RUN_B;AAA;1d;2026-05-01;2026-05-01;Bearish Divergence;CANDLE;NOISE;B;UP;NORMAL;BOS_UP;3;8;1;0;1;0",
        "technical_signal_relevance_export;RUN_B;BBB;1d;2026-05-02;2026-05-02;Hammer;CANDLE;WEAK_CONTEXT;A;UP;NORMAL;BOS_UP;3;8;1;0;1;0",
    ]


def test_export_cli_filtering_by_run_id_works(tmp_path, capsys):
    db_path = _db_path(tmp_path)
    conn = _connect(db_path)
    _insert_run(conn, "RUN_A")
    _insert_run(conn, "RUN_B")
    _insert_record(conn, run_id="RUN_A", ticker="AAA", signal_date="2026-05-01", signal_name="Hammer", relevance_class="RELEVANT", relevance_reason="A")
    _insert_record(conn, run_id="RUN_B", ticker="BBB", signal_date="2026-05-02", signal_name="Hammer", relevance_class="RELEVANT", relevance_reason="B")
    conn.commit()
    conn.close()

    main(["--analysis-db", str(db_path), "--run-id", "RUN_B"])

    output = capsys.readouterr().out
    assert "RUN_B;BBB" in output
    assert "RUN_A;AAA" not in output


def test_export_cli_filtering_by_ticker_works_with_comma_separated_tickers(tmp_path, capsys):
    db_path = _db_path(tmp_path)
    conn = _connect(db_path)
    _insert_run(conn, "RUN_A")
    _insert_record(conn, run_id="RUN_A", ticker="AAA", signal_date="2026-05-01", signal_name="Hammer", relevance_class="RELEVANT", relevance_reason="A")
    _insert_record(conn, run_id="RUN_A", ticker="BBB", signal_date="2026-05-02", signal_name="Hammer", relevance_class="RELEVANT", relevance_reason="B")
    _insert_record(conn, run_id="RUN_A", ticker="CCC", signal_date="2026-05-03", signal_name="Hammer", relevance_class="RELEVANT", relevance_reason="C")
    conn.commit()
    conn.close()

    main(["--analysis-db", str(db_path), "--ticker", "AAA, CCC"])

    output = capsys.readouterr().out
    assert "AAA" in output
    assert "CCC" in output
    assert "BBB" not in output


def test_export_cli_filtering_by_ticker_works_with_spaces_in_one_argument(tmp_path, capsys):
    db_path = _db_path(tmp_path)
    conn = _connect(db_path)
    _insert_run(conn, "RUN_A")
    _insert_record(conn, run_id="RUN_A", ticker="AAA", signal_date="2026-05-01", signal_name="Hammer", relevance_class="RELEVANT", relevance_reason="A")
    _insert_record(conn, run_id="RUN_A", ticker="BBB", signal_date="2026-05-02", signal_name="Hammer", relevance_class="RELEVANT", relevance_reason="B")
    _insert_record(conn, run_id="RUN_A", ticker="CCC", signal_date="2026-05-03", signal_name="Hammer", relevance_class="RELEVANT", relevance_reason="C")
    conn.commit()
    conn.close()

    main(["--analysis-db", str(db_path), "--ticker", "AAA, CCC"])

    summary = _summary(capsys.readouterr().out)
    assert summary["technical_signal_relevance_export.ticker_count_filter"] == "2"


def test_export_cli_filtering_by_shell_split_ticker_tokens_works(tmp_path, capsys):
    db_path = _db_path(tmp_path)
    conn = _connect(db_path)
    _insert_run(conn, "RUN_A")
    _insert_record(conn, run_id="RUN_A", ticker="AAA", signal_date="2026-05-01", signal_name="Hammer", relevance_class="RELEVANT", relevance_reason="A")
    _insert_record(conn, run_id="RUN_A", ticker="BBB", signal_date="2026-05-02", signal_name="Hammer", relevance_class="RELEVANT", relevance_reason="B")
    _insert_record(conn, run_id="RUN_A", ticker="CCC", signal_date="2026-05-03", signal_name="Hammer", relevance_class="RELEVANT", relevance_reason="C")
    conn.commit()
    conn.close()

    main(["--analysis-db", str(db_path), "--ticker", "AAA,", "CCC", "--timeframe", "1d"])

    output = capsys.readouterr().out
    assert "AAA" in output
    assert "CCC" in output
    assert "BBB" not in output
    summary = _summary(output)
    assert summary["technical_signal_relevance_export.ticker_count_filter"] == "2"


def test_export_cli_filtering_by_relevance_class_works(tmp_path, capsys):
    db_path = _db_path(tmp_path)
    conn = _connect(db_path)
    _insert_run(conn, "RUN_A")
    _insert_record(conn, run_id="RUN_A", ticker="AAA", signal_date="2026-05-01", signal_name="Hammer", relevance_class="RELEVANT", relevance_reason="A")
    _insert_record(conn, run_id="RUN_A", ticker="BBB", signal_date="2026-05-02", signal_name="Hammer", relevance_class="NOISE", relevance_reason="B")
    conn.commit()
    conn.close()

    main(["--analysis-db", str(db_path), "--relevance-class", "NOISE"])

    output = capsys.readouterr().out
    assert ";NOISE;" in output
    assert ";RELEVANT;" not in output


def test_export_cli_date_range_filtering_works(tmp_path, capsys):
    db_path = _db_path(tmp_path)
    conn = _connect(db_path)
    _insert_run(conn, "RUN_A")
    _insert_record(conn, run_id="RUN_A", ticker="AAA", signal_date="2026-05-01", signal_name="Hammer", relevance_class="RELEVANT", relevance_reason="A")
    _insert_record(conn, run_id="RUN_A", ticker="AAA", signal_date="2026-05-10", signal_name="Morning Star", relevance_class="RELEVANT", relevance_reason="B")
    conn.commit()
    conn.close()

    main(["--analysis-db", str(db_path), "--start-date", "2026-05-05", "--end-date", "2026-05-20"])

    output = capsys.readouterr().out
    assert "Morning Star" in output
    assert "2026-05-01;2026-05-01;Hammer" not in output


def test_export_cli_limit_works(tmp_path, capsys):
    db_path = _db_path(tmp_path)
    conn = _connect(db_path)
    _insert_run(conn, "RUN_A")
    _insert_record(conn, run_id="RUN_A", ticker="AAA", signal_date="2026-05-01", signal_name="Hammer", relevance_class="RELEVANT", relevance_reason="A")
    _insert_record(conn, run_id="RUN_A", ticker="BBB", signal_date="2026-05-02", signal_name="Morning Star", relevance_class="RELEVANT", relevance_reason="B")
    conn.commit()
    conn.close()

    main(["--analysis-db", str(db_path), "--limit", "1"])

    output = capsys.readouterr().out
    summary = _summary(output)
    assert summary["technical_signal_relevance_export.rows_returned"] == "1"


def test_export_cli_include_rule_trace_appends_rule_trace_column(tmp_path, capsys):
    db_path = _db_path(tmp_path)
    conn = _connect(db_path)
    _insert_run(conn, "RUN_A")
    _insert_record(
        conn,
        run_id="RUN_A",
        ticker="AAA",
        signal_date="2026-05-01",
        signal_name="Hammer",
        relevance_class="RELEVANT",
        relevance_reason="A",
        rule_trace='["missing_bar_index=false"]',
    )
    conn.commit()
    conn.close()

    main(["--analysis-db", str(db_path), "--include-rule-trace"])

    lines = capsys.readouterr().out.splitlines()
    assert lines[1].endswith(";rule_trace")
    assert lines[2].endswith(';["missing_bar_index=false"]')


def test_export_cli_summary_lines_are_printed_and_match_rows_returned(tmp_path, capsys):
    db_path = _db_path(tmp_path)
    conn = _connect(db_path)
    _insert_run(conn, "RUN_A")
    _insert_record(conn, run_id="RUN_A", ticker="AAA", signal_date="2026-05-01", signal_name="Hammer", relevance_class="RELEVANT", relevance_reason="A")
    conn.commit()
    conn.close()

    main(["--analysis-db", str(db_path), "--run-id", "RUN_A"])

    summary = _summary(capsys.readouterr().out)
    assert summary["technical_signal_relevance_export.rows_returned"] == "1"
    assert summary["technical_signal_relevance_export.run_id_filter"] == "RUN_A"
    assert summary["technical_signal_relevance_export.status"] == "OK"


def test_export_cli_invalid_relevance_class_exits_non_zero_and_prints_failed(tmp_path, capsys):
    db_path = _db_path(tmp_path)

    result = main(["--analysis-db", str(db_path), "--relevance-class", "BAD"])

    output = capsys.readouterr().out
    assert result == 1
    assert "SUMMARY technical_signal_relevance_export.status=FAILED" in output


def test_export_cli_invalid_date_range_exits_non_zero_and_prints_failed(tmp_path, capsys):
    db_path = _db_path(tmp_path)

    result = main(
        [
            "--analysis-db",
            str(db_path),
            "--start-date",
            "2026-05-10",
            "--end-date",
            "2026-05-01",
        ]
    )

    output = capsys.readouterr().out
    assert result == 1
    assert "SUMMARY technical_signal_relevance_export.status=FAILED" in output


def test_export_cli_empty_ticker_filter_exits_non_zero_and_prints_failed(tmp_path, capsys):
    db_path = _db_path(tmp_path)

    result = main(["--analysis-db", str(db_path), "--ticker", " , "])

    output = capsys.readouterr().out
    assert result == 1
    assert "SUMMARY technical_signal_relevance_export.status=FAILED" in output


def test_export_cli_is_read_only_and_does_not_add_run_or_relevance_rows(tmp_path, capsys):
    db_path = _db_path(tmp_path)
    conn = _connect(db_path)
    _insert_run(conn, "RUN_A")
    _insert_record(conn, run_id="RUN_A", ticker="AAA", signal_date="2026-05-01", signal_name="Hammer", relevance_class="RELEVANT", relevance_reason="A")
    conn.commit()
    before_run_count = _table_count(conn, "technical_signal_relevance_runs")
    before_record_count = _table_count(conn, "technical_signal_relevance")
    conn.close()

    result = main(["--analysis-db", str(db_path), "--run-id", "RUN_A"])

    assert result == 0
    capsys.readouterr()
    conn = _connect(db_path)
    assert _table_count(conn, "technical_signal_relevance_runs") == before_run_count
    assert _table_count(conn, "technical_signal_relevance") == before_record_count
    conn.close()
