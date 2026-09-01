from __future__ import annotations

import dataclasses
import inspect
import sqlite3
from pathlib import Path

import pytest

from rawcandle.cli.run_fundamentals_v4_lifecycle_revised import _validate, build_parser, run
from rawcandle.fundamentals.lifecycle.engine import MODEL_FINGERPRINT, LifecycleObservation
from rawcandle.fundamentals.lifecycle.revised_history import (
    HISTORY_MODE,
    RevisedLifecycleRepository,
    RevisedSource,
    build_revised_results,
    ensure_revised_schema,
    fiscal_sequence,
    load_revised_source,
    logical_fingerprint,
    quick_check,
    refresh_revised_history,
    replace_revised_results,
)


def _canonical(path: Path, *, duplicate: bool = False, bad_ready_input: bool = False) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE company(company_id INTEGER PRIMARY KEY);
        CREATE TABLE security(security_id INTEGER PRIMARY KEY,company_id INTEGER,current_ticker TEXT);
        CREATE TABLE v4_quarter(quarter_id INTEGER PRIMARY KEY,company_id INTEGER,fiscal_year INTEGER,fiscal_quarter TEXT,period_end TEXT);
        CREATE TABLE v4_quarter_financials(quarter_id INTEGER PRIMARY KEY,revenue REAL);
        CREATE TABLE v4_ttm_values(
          ttm_id INTEGER PRIMARY KEY,company_id INTEGER,security_id INTEGER,endpoint_quarter_id INTEGER,
          endpoint_fiscal_year INTEGER,endpoint_fiscal_quarter TEXT,period_end TEXT,model_version TEXT,
          core_ttm_ready INTEGER,ttm_source_available_date TEXT,ttm_revenue REAL,ttm_ebit REAL,
          ttm_free_cashflow REAL,input_values_hash TEXT,output_fingerprint TEXT);
        CREATE TABLE v4_ttm_input_quarter(
          ttm_id INTEGER,input_position INTEGER,input_quarter_id INTEGER,input_values_hash TEXT);
        """
    )
    conn.execute("INSERT INTO company VALUES(1)")
    conn.execute("INSERT INTO security VALUES(10,1,'AAA')")
    for index in range(1, 10):
        year = 2022 + (index - 1) // 4
        quarter = f"Q{(index - 1) % 4 + 1}"
        conn.execute("INSERT INTO v4_quarter VALUES(?,?,?,?,?)", (index, 1, year, quarter, f"{year}-0{(index - 1) % 4 + 1}-28"))
        conn.execute("INSERT INTO v4_quarter_financials VALUES(?,?)", (index, 0 if index <= 4 else 25))
        inputs = list(range(max(1, index - 3), index + 1))
        ready = int(len(inputs) == 4)
        conn.execute(
            "INSERT INTO v4_ttm_values VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (index, 1, 10, index, year, quarter, f"{year}-0{(index - 1) % 4 + 1}-28", "V4_TTM_EBIT_FIRST_V1",
             ready, f"{year}-10-01", 0 if index == 4 else 100 + index * 10, -10 if index == 4 else 20,
             -8 if index == 4 else 10, f"ih{index}", f"oh{index}"),
        )
        for position, quarter_id in enumerate(inputs, 1):
            if bad_ready_input and index == 9 and position == 4:
                continue
            conn.execute("INSERT INTO v4_ttm_input_quarter VALUES(?,?,?,?)", (index, position, quarter_id, f"q{quarter_id}"))
    if duplicate:
        conn.execute(
            "INSERT INTO v4_ttm_values VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (99, 1, 10, 99, 2024, "Q1", "2024-01-28", "V4_TTM_EBIT_FIRST_V1", 0, None, None, None, None, "x", "x"),
        )
    conn.commit()
    conn.close()


def _observation(index: int, *, revenue: float = 100.0, ebit: float = 10.0, fcf: float = 5.0) -> LifecycleObservation:
    year = 2022 + (index - 1) // 4
    quarter = f"Q{(index - 1) % 4 + 1}"
    return LifecycleObservation(
        company_id=1, security_id=10, endpoint_quarter_id=index, endpoint_fiscal_year=year,
        endpoint_fiscal_quarter=quarter, period_end=f"{year}-01-01", source_available_date=f"{year}-10-01",
        source_data_version=f"source-{index}", core_ttm_ready=True, ttm_revenue=revenue,
        ttm_ebit=ebit, ttm_free_cashflow=fcf, lag4_ttm_revenue=100.0,
        lag4_ttm_ebit=10.0, lag4_chain_valid=True, input_quarter_revenues=(25.0,) * 4,
    )


def _source(observations: tuple[LifecycleObservation, ...]) -> RevisedSource:
    return RevisedSource(
        observations,
        {item.endpoint_quarter_id: "AAA" for item in observations},
        {item.endpoint_quarter_id: fiscal_sequence(item.endpoint_fiscal_year, item.endpoint_fiscal_quarter) for item in observations},
        "source-fingerprint",
    )


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_revised_schema(conn)
    return conn


def test_adapter_uses_fiscal_order_exact_lag4_and_four_quarter_inputs(tmp_path: Path) -> None:
    path = tmp_path / "canonical.db"
    _canonical(path)
    source = load_revised_source(path)
    assert [item.endpoint_quarter_id for item in source.observations] == list(range(1, 10))
    row = source.observations[-1]
    assert row.lag4_chain_valid and row.lag4_ttm_revenue == 150
    assert row.input_quarter_revenues == (25.0, 25.0, 25.0, 25.0)
    assert source.observations[3].input_quarter_revenues == (0.0, 0.0, 0.0, 0.0)


def test_adapter_missing_lag4_and_pre_revenue_are_classified_honestly(tmp_path: Path) -> None:
    path = tmp_path / "canonical.db"
    _canonical(path)
    source = load_revised_source(path, tickers=["aaa"])
    rows = build_revised_results(source, generated_at="now")
    assert rows[0]["raw_state"] == "UNCLASSIFIED"
    assert rows[3]["raw_state"] == "STARTUP"
    assert rows[3]["startup_profile"] == "PRE_REVENUE"


def test_adapter_filters_by_stable_company_and_rejects_unknown_ticker(tmp_path: Path) -> None:
    path = tmp_path / "canonical.db"
    _canonical(path)
    assert len(load_revised_source(path, company_ids=[1]).observations) == 9
    with pytest.raises(ValueError, match="TICKER_NOT_FOUND"):
        load_revised_source(path, tickers=["MISSING"])


def test_adapter_rejects_duplicate_fiscal_winner_and_broken_ready_input(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.db"
    _canonical(duplicate, duplicate=True)
    with pytest.raises(ValueError, match="DUPLICATE_CANONICAL"):
        load_revised_source(duplicate)
    broken = tmp_path / "broken.db"
    _canonical(broken, bad_ready_input=True)
    with pytest.raises(ValueError, match="BROKEN_READY_TTM_INPUT_CHAIN"):
        load_revised_source(broken)


def test_replay_unclassified_clears_public_state_but_retains_audit_state() -> None:
    observations = (_observation(1), dataclasses.replace(_observation(2), source_available_date=None))
    rows = build_revised_results(_source(observations), generated_at="now")
    assert rows[1]["raw_state"] == "UNCLASSIFIED"
    assert rows[1]["final_state"] is None
    assert rows[1]["last_confirmed_state"] == rows[0]["final_state"]
    assert rows[1]["candidate_count"] == 0


def test_replay_distressed_entry_and_two_observation_exit() -> None:
    observations = (
        _observation(1),
        _observation(2, ebit=-30, fcf=-30),
        _observation(3),
        _observation(4),
    )
    rows = build_revised_results(_source(observations), generated_at="now")
    assert rows[1]["final_state"] == "DISTRESSED"
    assert rows[2]["final_state"] == "DISTRESSED"
    assert rows[3]["final_state"] == rows[3]["raw_state"]


def test_replay_is_deterministic_and_historical_change_can_change_later_state() -> None:
    original = (_observation(1), _observation(2), _observation(3))
    first = build_revised_results(_source(original), generated_at="one")
    second = build_revised_results(_source(original), generated_at="two")
    assert logical_fingerprint(first) == logical_fingerprint(second)
    changed = (original[0], _observation(2, ebit=-30, fcf=-30), original[2])
    changed_rows = build_revised_results(_source(changed))
    assert logical_fingerprint(first) != logical_fingerprint(changed_rows)
    assert first[2]["final_state"] != changed_rows[2]["final_state"]


def test_persistence_fresh_replace_idempotency_stale_removal_and_readers() -> None:
    conn = _db()
    rows = build_revised_results(_source((_observation(1), _observation(2))), generated_at="now")
    first = replace_revised_results(conn, rows)
    conn.commit()
    assert first.rows_inserted == 2
    second = replace_revised_results(conn, rows)
    assert second.rows_inserted == 0 and second.rows_unchanged == 2
    repo = RevisedLifecycleRepository(conn)
    assert repo.current_company(1, model_fingerprint=MODEL_FINGERPRINT)["quarter_id"] == 2
    assert len(repo.current_universe(model_fingerprint=MODEL_FINGERPRINT)) == 1
    assert len(repo.history(1, model_fingerprint=MODEL_FINGERPRINT)) == 2
    assert repo.fiscal_quarter(1, 2022, "Q1", model_fingerprint=MODEL_FINGERPRINT)["quarter_id"] == 1
    replace_revised_results(conn, rows[:1])
    assert len(repo.history(1, model_fingerprint=MODEL_FINGERPRINT)) == 1


def test_persistence_preserves_parallel_fingerprint() -> None:
    conn = _db()
    rows = build_revised_results(_source((_observation(1),)), generated_at="now")
    replace_revised_results(conn, rows)
    columns = [row[1] for row in conn.execute("PRAGMA table_info(lifecycle_revised_result)") if row[1] != "lifecycle_revised_result_id"]
    values = dict(conn.execute("SELECT * FROM lifecycle_revised_result").fetchone())
    values["model_fingerprint"] = "other"
    conn.execute(
        f"INSERT INTO lifecycle_revised_result({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
        [values[column] for column in columns],
    )
    replace_revised_results(conn, rows)
    assert conn.execute("SELECT COUNT(*) FROM lifecycle_revised_result WHERE model_fingerprint='other'").fetchone()[0] == 1


def test_scoped_replace_preserves_unselected_companies() -> None:
    conn = _db()
    first_company = build_revised_results(_source((_observation(1),)), generated_at="now")
    second_observation = dataclasses.replace(_observation(1), company_id=2, security_id=20, endpoint_quarter_id=20)
    second_source = RevisedSource((second_observation,), {20: "BBB"}, {20: fiscal_sequence(2022, "Q1")}, "source-2")
    second_company = build_revised_results(second_source, generated_at="now")
    replace_revised_results(conn, [*first_company, *second_company])
    replace_revised_results(conn, [], company_scope=[1])
    assert conn.execute("SELECT company_id FROM lifecycle_revised_result").fetchall()[0][0] == 2


def test_validation_failure_does_not_replace_committed_rows() -> None:
    conn = _db()
    rows = build_revised_results(_source((_observation(1),)), generated_at="now")
    replace_revised_results(conn, rows)
    conn.commit()
    bad = [dict(rows[0], history_mode="WRONG")]
    with pytest.raises(ValueError, match="INVALID_HISTORY_MODE"):
        replace_revised_results(conn, bad)
    assert conn.execute("SELECT COUNT(*) FROM lifecycle_revised_result").fetchone()[0] == 1


def test_insert_failure_rolls_back_deleted_rows() -> None:
    conn = _db()
    rows = build_revised_results(_source((_observation(1),)), generated_at="now")
    replace_revised_results(conn, rows)
    conn.commit()
    changed = [dict(rows[0], source_input_fingerprint="changed", generated_at_utc=None)]
    with pytest.raises(sqlite3.IntegrityError):
        replace_revised_results(conn, changed)
    stored = conn.execute("SELECT source_input_fingerprint FROM lifecycle_revised_result").fetchone()[0]
    assert stored == rows[0]["source_input_fingerprint"]


def test_latest_unclassified_reader_does_not_fall_back() -> None:
    conn = _db()
    observations = (_observation(1), dataclasses.replace(_observation(2), source_available_date=None))
    rows = build_revised_results(_source(observations), generated_at="now")
    replace_revised_results(conn, rows)
    current = RevisedLifecycleRepository(conn).current_company(1, model_fingerprint=MODEL_FINGERPRINT)
    assert current["lifecycle_status"] == "LIFECYCLE_NOT_READY"
    assert current["final_state"] is None
    repo = RevisedLifecycleRepository(conn)
    assert len(repo.current_universe(
        model_fingerprint=MODEL_FINGERPRINT,
        lifecycle_status="LIFECYCLE_NOT_READY",
    )) == 1
    assert repo.current_universe(
        model_fingerprint=MODEL_FINGERPRINT,
        lifecycle_class="MATURE",
    ) == []


def test_invalid_availability_negative_and_non_finite_inputs_follow_engine_contract() -> None:
    observations = (
        dataclasses.replace(_observation(1), source_available_date="invalid"),
        dataclasses.replace(_observation(2), ttm_revenue=-1.0),
        dataclasses.replace(_observation(3), ttm_ebit=float("inf")),
    )
    rows = build_revised_results(_source(observations), generated_at="now")
    assert [row["reason_code"] for row in rows] == [
        "SOURCE_AVAILABILITY_DATE_INVALID",
        "CURRENT_REVENUE_NEGATIVE",
        "CURRENT_EBIT_INVALID",
    ]


def test_quick_check_reconciles_direct_replay() -> None:
    conn = _db()
    rows = build_revised_results(_source((_observation(1), _observation(2))), generated_at="now")
    replace_revised_results(conn, rows)
    result = quick_check(conn, expected_rows=rows)
    assert result["ok"] and result["sqlite_quick_check"] == "ok"


def test_cli_is_dry_by_default_and_requires_explicit_scope_and_destination(tmp_path: Path) -> None:
    path = tmp_path / "canonical.db"
    _canonical(path)
    parser = build_parser()
    args = parser.parse_args(["--canonical-db", str(path), "--ticker", "AAA"])
    assert run(args)["mode"] == "PLAN"
    args = parser.parse_args(["--canonical-db", str(path), "--ticker", "AAA", "--apply"])
    with pytest.raises(ValueError, match="EXPLICIT_DESTINATION"):
        run(args)
    args = parser.parse_args(["--canonical-db", str(path)])
    with pytest.raises(ValueError, match="EXPLICIT_SCOPE"):
        run(args)


def test_cli_blocks_phase_2c_production_destination(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical.db"
    _canonical(canonical)
    production = Path(__file__).resolve().parents[1] / "data" / "fundamentals_analysis.db"
    args = build_parser().parse_args([
        "--canonical-db", str(canonical), "--destination-db", str(production),
        "--ticker", "AAA", "--apply",
    ])
    with pytest.raises(ValueError, match="PRODUCTION_APPLY_REQUIRES_CONFIRMATION"):
        run(args)


def test_production_authorization_guards_fail_closed(tmp_path: Path) -> None:
    parser = build_parser()
    root = Path(__file__).resolve().parents[1]
    canonical = root / "data" / "fundamentals_v4.db"
    production = root / "data" / "fundamentals_analysis.db"
    fingerprint = MODEL_FINGERPRINT

    with pytest.raises(ValueError, match="ONLY_AUTHORIZES_EXACT"):
        _validate(parser.parse_args([
            "--canonical-db", str(canonical), "--destination-db", str(tmp_path / "temp.db"),
            "--full-universe", "--model-fingerprint", fingerprint, "--apply", "--confirm-production",
        ]))
    with pytest.raises(ValueError, match="EXPLICIT_MODEL_FINGERPRINT"):
        _validate(parser.parse_args([
            "--canonical-db", str(canonical), "--destination-db", str(production),
            "--full-universe", "--apply", "--confirm-production",
        ]))
    with pytest.raises(ValueError, match="FINGERPRINT_MISMATCH"):
        _validate(parser.parse_args([
            "--canonical-db", str(canonical), "--destination-db", str(production),
            "--full-universe", "--model-fingerprint", "wrong", "--apply", "--confirm-production",
        ]))
    with pytest.raises(ValueError, match="FULL_UNIVERSE"):
        _validate(parser.parse_args([
            "--canonical-db", str(canonical), "--destination-db", str(production), "--company-id", "1",
            "--model-fingerprint", fingerprint, "--apply", "--confirm-production",
        ]))
    fake_canonical = tmp_path / "canonical.db"
    _canonical(fake_canonical)
    with pytest.raises(ValueError, match="AUTHORIZED_CANONICAL"):
        _validate(parser.parse_args([
            "--canonical-db", str(fake_canonical), "--destination-db", str(production),
            "--full-universe", "--model-fingerprint", fingerprint, "--apply", "--confirm-production",
        ]))
    with pytest.raises(ValueError, match="MARKET_DATABASE_DESTINATION_BLOCKED"):
        _validate(parser.parse_args([
            "--canonical-db", str(canonical), "--destination-db", str(root / "data" / "osakedata.db"),
            "--full-universe", "--apply",
        ]))


def test_confirmed_production_arguments_pass_read_only_validation() -> None:
    root = Path(__file__).resolve().parents[1]
    args = build_parser().parse_args([
        "--canonical-db", str(root / "data" / "fundamentals_v4.db"),
        "--destination-db", str(root / "data" / "fundamentals_analysis.db"),
        "--full-universe", "--model-fingerprint", MODEL_FINGERPRINT,
        "--apply", "--confirm-production",
    ])
    _validate(args)


def test_cli_filtered_apply_runs_twice_and_is_deterministic(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical.db"
    destination = tmp_path / "analysis.db"
    _canonical(canonical)
    args = build_parser().parse_args([
        "--canonical-db", str(canonical), "--destination-db", str(destination),
        "--ticker", "AAA", "--apply",
    ])
    result = run(args)
    assert result["first_quick_check"]["ok"]
    assert result["second_apply"]["rows_inserted"] == 0
    assert result["first_apply"]["result_fingerprint"] == result["second_apply"]["result_fingerprint"]
    plan_args = build_parser().parse_args([
        "--canonical-db", str(canonical), "--destination-db", str(destination), "--ticker", "AAA",
    ])
    plan = run(plan_args)
    assert plan["planned"]["rows_inserted"] == 0
    assert plan["planned"]["rows_unchanged"] == 9


def test_refresh_full_universe_is_idempotent_and_reports_fallback(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical.db"
    analysis = tmp_path / "analysis.db"
    _canonical(canonical)
    first = refresh_revised_history(canonical, analysis)
    second = refresh_revised_history(canonical, analysis)
    assert first.scope == second.scope == "FULL_UNIVERSE_FALLBACK"
    assert first.rows_inserted == 9
    assert second.rows_inserted == 0 and second.rows_unchanged == 9
    assert first.result_fingerprint == second.result_fingerprint
    selected = refresh_revised_history(canonical, analysis, company_ids=[1])
    assert selected.scope == "CHANGED_COMPANIES"
    assert selected.companies == 1 and selected.rows_unchanged == 9


def test_active_lifecycle_writer_does_not_use_legacy_table() -> None:
    import rawcandle.fundamentals.lifecycle.revised_history as revised

    source = inspect.getsource(revised)
    assert "INSERT INTO lifecycle_result" not in source
    assert "DELETE FROM lifecycle_result" not in source


def test_refresh_failure_preserves_lifecycle_and_unrelated_committed_data(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical.db"
    analysis = tmp_path / "analysis.db"
    _canonical(canonical)
    refresh_revised_history(canonical, analysis)
    with sqlite3.connect(analysis) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE score_guard(value TEXT)")
        conn.execute("INSERT INTO score_guard VALUES('committed')")
        before = logical_fingerprint([dict(row) for row in conn.execute(
            "SELECT * FROM lifecycle_revised_result ORDER BY company_id,fiscal_sequence"
        )])
        conn.execute(
            "CREATE TRIGGER fail_lifecycle_insert BEFORE INSERT ON lifecycle_revised_result "
            "BEGIN SELECT RAISE(FAIL,'forced lifecycle failure'); END"
        )
        conn.commit()
    with sqlite3.connect(canonical) as conn:
        conn.execute("UPDATE v4_ttm_values SET ttm_revenue=ttm_revenue+1 WHERE ttm_id=9")
        conn.commit()
    with pytest.raises(sqlite3.IntegrityError, match="forced lifecycle failure"):
        refresh_revised_history(canonical, analysis)
    with sqlite3.connect(analysis) as conn:
        conn.row_factory = sqlite3.Row
        after = logical_fingerprint([dict(row) for row in conn.execute(
            "SELECT * FROM lifecycle_revised_result ORDER BY company_id,fiscal_sequence"
        )])
        assert before == after
        assert conn.execute("SELECT value FROM score_guard").fetchone()[0] == "committed"
