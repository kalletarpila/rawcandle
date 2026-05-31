import contextlib
import io
import sqlite3
from pathlib import Path

from dev_tools import run_report_canonical_v2_all_outputs_smoke as smoke_cli


def _create_source_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """
        CREATE TABLE dc_group_swing_signal_daily (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            signal_version TEXT NOT NULL,
            market TEXT NULL,
            group_type TEXT NOT NULL,
            group_name TEXT NOT NULL,
            parent_group_type TEXT NULL,
            parent_group_name TEXT NULL,
            timing_state TEXT NULL,
            overheat_risk_level TEXT NULL,
            return_2d REAL NULL,
            return_5d REAL NULL,
            return_30d REAL NULL,
            ema20_breadth_delta_5d REAL NULL,
            ma10_breadth_delta_5d REAL NULL,
            trend_breadth REAL NULL,
            weakness_breadth REAL NULL,
            strength_breadth REAL NULL,
            data_quality_status TEXT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dc_group_synthetic_ohlc_daily (
            ohlc_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            calc_version TEXT NOT NULL,
            market TEXT NULL,
            group_type TEXT NOT NULL,
            group_name TEXT NOT NULL,
            synthetic_close REAL NULL,
            distance_to_ema20_pct REAL NULL,
            distance_to_ema50_pct REAL NULL,
            trend_classification TEXT NULL,
            latest_structure_label TEXT NULL,
            latest_bos_event_type TEXT NULL,
            latest_bos_freshness TEXT NULL,
            latest_reset_reason TEXT NULL,
            latest_reset_freshness TEXT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dc_ticker_swing_signal_daily (
            signal_date TEXT NOT NULL,
            taxonomy_version TEXT NOT NULL,
            signal_version TEXT NOT NULL,
            market TEXT NULL,
            ticker TEXT NOT NULL,
            primary_layer TEXT NULL,
            primary_subindustry TEXT NULL,
            close REAL NULL,
            ema20 REAL NULL,
            price_data_status TEXT NULL,
            latest_bullish_relevance_class TEXT NULL,
            latest_bearish_relevance_class TEXT NULL,
            breakout_signal INTEGER NULL,
            pullback_signal INTEGER NULL,
            fast_ema10_pullback_signal INTEGER NULL,
            conservative_ema20_pullback_signal INTEGER NULL,
            exit_risk_signal INTEGER NULL,
            exit_risk_severity TEXT NULL,
            exit_reason TEXT NULL,
            bullish_candle_signal INTEGER NULL,
            bullish_divergence_signal INTEGER NULL,
            hidden_bullish_divergence_signal INTEGER NULL,
            bearish_candle_signal INTEGER NULL,
            bearish_divergence_signal INTEGER NULL,
            hidden_bearish_divergence_signal INTEGER NULL,
            return_5d REAL NULL,
            return_10d REAL NULL,
            return_20d REAL NULL,
            return_60d REAL NULL,
            distance_to_ema20_pct REAL NULL,
            distance_to_ema50_pct REAL NULL,
            ticker_trend_state TEXT NULL,
            latest_structure_label TEXT NULL,
            latest_structure_freshness TEXT NULL,
            latest_bos_event_type TEXT NULL,
            latest_bos_event_date TEXT NULL,
            latest_bos_age_trading_days INTEGER NULL,
            latest_bos_freshness TEXT NULL,
            latest_reset_reason TEXT NULL,
            latest_reset_event_date TEXT NULL,
            latest_reset_age_trading_days INTEGER NULL,
            latest_reset_freshness TEXT NULL
        )
        """
    )
    return conn


def _insert_group_row(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    market: str,
    group_type: str,
    group_name: str,
    parent_group_type: str | None,
    parent_group_name: str | None,
    timing_state: str = "BUY_ZONE",
    overheat_risk_level: str = "LOW",
) -> None:
    conn.execute(
        """
        INSERT INTO dc_group_swing_signal_daily (
            signal_date, taxonomy_version, signal_version, market, group_type, group_name,
            parent_group_type, parent_group_name, timing_state, overheat_risk_level,
            return_2d, return_5d, return_30d, ema20_breadth_delta_5d, ma10_breadth_delta_5d,
            trend_breadth, weakness_breadth, strength_breadth, data_quality_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signal_date,
            "DC_TAXONOMY_FULL_V1",
            "DC_SWING_SIGNAL_V1",
            market,
            group_type,
            group_name,
            parent_group_type,
            parent_group_name,
            timing_state,
            overheat_risk_level,
            1.0,
            2.0,
            3.0,
            0.2,
            0.1,
            0.8,
            0.1,
            0.7,
            "OK",
        ),
    )


def _insert_synthetic_row(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    market: str,
    group_type: str,
    group_name: str,
) -> None:
    conn.execute(
        """
        INSERT INTO dc_group_synthetic_ohlc_daily (
            ohlc_date, taxonomy_version, calc_version, market, group_type, group_name,
            synthetic_close, distance_to_ema20_pct, distance_to_ema50_pct, trend_classification,
            latest_structure_label, latest_bos_event_type, latest_bos_freshness,
            latest_reset_reason, latest_reset_freshness
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signal_date,
            "DC_TAXONOMY_FULL_V1",
            "DC_SWING_OHLC_V1",
            market,
            group_type,
            group_name,
            150.0,
            1.2,
            3.4,
            "UP",
            "HL",
            "BOS_UP",
            "FRESH",
            "NONE",
            "STALE",
        ),
    )


def _insert_ticker_row(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    market: str,
    ticker: str = "NVDA",
    breakout_signal: int = 0,
    pullback_signal: int = 0,
    fast_ema10_pullback_signal: int = 0,
    conservative_ema20_pullback_signal: int = 0,
    exit_risk_signal: int = 0,
    exit_risk_severity: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO dc_ticker_swing_signal_daily (
            signal_date, taxonomy_version, signal_version, market, ticker,
            primary_layer, primary_subindustry, close, ema20, price_data_status,
            latest_bullish_relevance_class, latest_bearish_relevance_class,
            breakout_signal, pullback_signal, fast_ema10_pullback_signal,
            conservative_ema20_pullback_signal, exit_risk_signal, exit_risk_severity,
            exit_reason, bullish_candle_signal, bullish_divergence_signal,
            hidden_bullish_divergence_signal, bearish_candle_signal,
            bearish_divergence_signal, hidden_bearish_divergence_signal,
            return_5d, return_10d, return_20d, return_60d, distance_to_ema20_pct,
            distance_to_ema50_pct, ticker_trend_state, latest_structure_label,
            latest_structure_freshness, latest_bos_event_type, latest_bos_event_date,
            latest_bos_age_trading_days, latest_bos_freshness, latest_reset_reason,
            latest_reset_event_date, latest_reset_age_trading_days, latest_reset_freshness
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signal_date,
            "DC_TAXONOMY_FULL_V1",
            "DC_SWING_SIGNAL_V1",
            market,
            ticker,
            "Infrastructure",
            "Semis",
            100.0,
            98.5,
            "OK",
            "RELEVANT",
            None,
            breakout_signal,
            pullback_signal,
            fast_ema10_pullback_signal,
            conservative_ema20_pullback_signal,
            exit_risk_signal,
            exit_risk_severity,
            "reason-token",
            1 if breakout_signal else 0,
            0,
            0,
            0,
            0,
            0,
            2.0,
            4.0,
            8.0,
            12.0,
            1.5,
            3.0,
            "UP",
            "HL",
            "FRESH",
            "BOS_UP",
            signal_date,
            0,
            "FRESH",
            "NONE",
            signal_date,
            0,
            "STALE",
        ),
    )


def _seed_source_rows(conn: sqlite3.Connection, *, market: str = "usa") -> None:
    for day in range(1, 31):
        signal_date = f"2026-05-{day:02d}"
        _insert_group_row(
            conn,
            signal_date=signal_date,
            market=market,
            group_type="layer",
            group_name="Infrastructure",
            parent_group_type="ecosystem",
            parent_group_name="Datacenter",
        )
        _insert_group_row(
            conn,
            signal_date=signal_date,
            market=market,
            group_type="subindustry",
            group_name="Semis",
            parent_group_type="layer",
            parent_group_name="Infrastructure",
        )
        _insert_synthetic_row(conn, signal_date=signal_date, market=market, group_type="layer", group_name="Infrastructure")
        _insert_synthetic_row(conn, signal_date=signal_date, market=market, group_type="subindustry", group_name="Semis")
        _insert_ticker_row(
            conn,
            signal_date=signal_date,
            market=market,
            breakout_signal=1 if day % 7 == 0 else 0,
            pullback_signal=1 if day % 5 == 0 else 0,
            fast_ema10_pullback_signal=1 if day % 10 == 0 else 0,
            conservative_ema20_pullback_signal=1 if day % 15 == 0 else 0,
            exit_risk_signal=1 if day % 6 == 0 else 0,
            exit_risk_severity="HIGH" if day % 6 == 0 else None,
        )
    conn.commit()


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = smoke_cli.main(argv)
    return exit_code, stdout.getvalue(), stderr.getvalue()


def _output_paths(output_dir: Path, signal_date: str) -> dict[str, Path]:
    return {
        "daily_markdown": output_dir / f"datacenter_daily_canonical_v2_{signal_date}.md",
        "daily_csv": output_dir / f"datacenter_daily_canonical_v2_{signal_date}.csv",
        "rolling2_markdown": output_dir / f"datacenter_rolling2_canonical_v2_{signal_date}.md",
        "rolling2_csv": output_dir / f"datacenter_rolling2_canonical_v2_{signal_date}.csv",
        "rolling5_markdown": output_dir / f"datacenter_rolling5_canonical_v2_{signal_date}.md",
        "rolling5_csv": output_dir / f"datacenter_rolling5_canonical_v2_{signal_date}.csv",
        "rolling30_markdown": output_dir / f"datacenter_rolling30_canonical_v2_{signal_date}.md",
        "rolling30_csv": output_dir / f"datacenter_rolling30_canonical_v2_{signal_date}.csv",
    }


def _fake_ok_parity(*args, **kwargs):
    return {
        "status": "OK",
        "signal_date": kwargs.get("signal_date"),
        "taxonomy_version": kwargs.get("taxonomy_version"),
        "market": kwargs.get("market"),
        "horizons": kwargs.get("horizons", ("daily", "rolling2", "rolling5", "rolling30")),
        "mismatch_count": 0,
        "missing_current_count": 0,
        "missing_v2_count": 0,
        "matched_count": 6,
        "horizon_summaries": {},
        "mismatches": [],
    }


def test_successful_all_output_smoke(tmp_path: Path, monkeypatch):
    source_db = tmp_path / "source.sqlite"
    temp_db = tmp_path / "temp.sqlite"
    output_dir = tmp_path / "outputs"
    summary_output = tmp_path / "nested" / "summary.txt"
    with _create_source_db(source_db) as conn:
        _seed_source_rows(conn, market="usa")

    monkeypatch.setattr(smoke_cli, "audit_report_canonical_v2_parity", _fake_ok_parity)

    exit_code, stdout, stderr = _run_cli(
        [
            "--source-db",
            str(source_db),
            "--temp-db",
            str(temp_db),
            "--output-dir",
            str(output_dir),
            "--signal-date",
            "2026-05-30",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--run-id",
            "smoke-run",
            "--market",
            "usa",
            "--summary-output",
            str(summary_output),
        ]
    )

    outputs = _output_paths(output_dir, "2026-05-30")

    assert exit_code == 0
    assert stderr == ""
    for path in outputs.values():
        assert path.exists()
        assert path.read_text(encoding="utf-8")
    assert summary_output.exists()
    assert "SUMMARY status=OK" in stdout
    assert "SUMMARY parity_status=OK" in stdout
    assert "SUMMARY output.daily_markdown.path=" in stdout
    assert "SUMMARY output.rolling30_csv.byte_count=" in stdout
    assert "SUMMARY status=OK" in summary_output.read_text(encoding="utf-8")


def test_source_db_is_not_modified(tmp_path: Path, monkeypatch):
    source_db = tmp_path / "source.sqlite"
    temp_db = tmp_path / "temp.sqlite"
    output_dir = tmp_path / "outputs"
    with _create_source_db(source_db) as conn:
        _seed_source_rows(conn, market="usa")
        before_ticker_count = conn.execute(
            "SELECT COUNT(*) AS row_count FROM dc_ticker_swing_signal_daily WHERE signal_date='2026-05-30' AND taxonomy_version='DC_TAXONOMY_FULL_V1' AND market='usa'"
        ).fetchone()["row_count"]
        before_tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }

    monkeypatch.setattr(smoke_cli, "audit_report_canonical_v2_parity", _fake_ok_parity)

    exit_code, stdout, stderr = _run_cli(
        [
            "--source-db",
            str(source_db),
            "--temp-db",
            str(temp_db),
            "--output-dir",
            str(output_dir),
            "--signal-date",
            "2026-05-30",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--run-id",
            "smoke-run",
            "--market",
            "usa",
        ]
    )

    assert exit_code == 0
    assert stderr == ""
    with sqlite3.connect(source_db) as conn:
        conn.row_factory = sqlite3.Row
        after_ticker_count = conn.execute(
            "SELECT COUNT(*) AS row_count FROM dc_ticker_swing_signal_daily WHERE signal_date='2026-05-30' AND taxonomy_version='DC_TAXONOMY_FULL_V1' AND market='usa'"
        ).fetchone()["row_count"]
        after_tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert before_ticker_count == after_ticker_count == 1
    assert "dc_report_run_v2" not in before_tables
    assert "dc_report_run_v2" not in after_tables


def test_overwrite_protections(tmp_path: Path, monkeypatch):
    source_db = tmp_path / "source.sqlite"
    temp_db = tmp_path / "temp.sqlite"
    output_dir = tmp_path / "outputs"
    outputs = _output_paths(output_dir, "2026-05-30")
    with _create_source_db(source_db) as conn:
        _seed_source_rows(conn, market="usa")
    temp_db.write_text("old", encoding="utf-8")
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs["daily_markdown"].write_text("old", encoding="utf-8")

    monkeypatch.setattr(smoke_cli, "audit_report_canonical_v2_parity", _fake_ok_parity)

    exit_code, stdout, stderr = _run_cli(
        [
            "--source-db",
            str(source_db),
            "--temp-db",
            str(temp_db),
            "--output-dir",
            str(output_dir),
            "--signal-date",
            "2026-05-30",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--run-id",
            "smoke-run",
            "--market",
            "usa",
        ]
    )
    assert exit_code == 1
    assert "already exists" in stderr

    exit_code, stdout, stderr = _run_cli(
        [
            "--source-db",
            str(source_db),
            "--temp-db",
            str(temp_db),
            "--output-dir",
            str(output_dir),
            "--signal-date",
            "2026-05-30",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--run-id",
            "smoke-run",
            "--market",
            "usa",
            "--overwrite-temp",
            "--overwrite-output",
        ]
    )
    assert exit_code == 0
    assert "SUMMARY status=OK" in stdout
    assert stderr == ""


def test_parity_mismatch_exits_nonzero(tmp_path: Path, monkeypatch):
    source_db = tmp_path / "source.sqlite"
    temp_db = tmp_path / "temp.sqlite"
    output_dir = tmp_path / "outputs"
    with _create_source_db(source_db) as conn:
        _seed_source_rows(conn, market="usa")

    def _fake_mismatch(*args, **kwargs):
        return {
            "status": "MISMATCH",
            "mismatch_count": 1,
            "missing_current_count": 0,
            "missing_v2_count": 0,
            "matched_count": 4,
            "mismatches": [
                {
                    "horizon": "daily",
                    "classification_type": "daily_trigger",
                    "ticker": "NVDA",
                    "field": "classification_state",
                    "current_value": "BUY_TRIGGER",
                    "v2_value": "BROKEN",
                    "reason": "field_mismatch",
                }
            ],
        }

    monkeypatch.setattr(smoke_cli, "audit_report_canonical_v2_parity", _fake_mismatch)

    exit_code, stdout, stderr = _run_cli(
        [
            "--source-db",
            str(source_db),
            "--temp-db",
            str(temp_db),
            "--output-dir",
            str(output_dir),
            "--signal-date",
            "2026-05-30",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--run-id",
            "smoke-run",
            "--market",
            "usa",
        ]
    )

    assert exit_code == 1
    assert "SUMMARY parity_status=MISMATCH" in stdout
    assert "SUMMARY parity_mismatch_count=1" in stdout
    assert (
        "MISMATCH horizon=daily classification_type=daily_trigger ticker=NVDA "
        "field=classification_state current=BUY_TRIGGER v2=BROKEN reason=field_mismatch"
    ) in stdout
    outputs = _output_paths(output_dir, "2026-05-30")
    assert all(not path.exists() for path in outputs.values())
    assert stderr == ""


def test_missing_source_data_exits_nonzero(tmp_path: Path):
    source_db = tmp_path / "source.sqlite"
    temp_db = tmp_path / "temp.sqlite"
    output_dir = tmp_path / "outputs"
    with _create_source_db(source_db):
        pass

    exit_code, stdout, stderr = _run_cli(
        [
            "--source-db",
            str(source_db),
            "--temp-db",
            str(temp_db),
            "--output-dir",
            str(output_dir),
            "--signal-date",
            "2026-05-30",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--run-id",
            "smoke-run",
            "--market",
            "usa",
        ]
    )

    assert exit_code == 1
    assert "SUMMARY source_ticker_rows=0" in stdout
    assert "required source data missing" in stderr


def test_invalid_args_and_invalid_db_return_usage_or_db_errors(tmp_path: Path):
    exit_code, stdout, stderr = _run_cli(["--source-db", str(tmp_path / "missing.sqlite")])
    assert exit_code == 2
    assert stdout == ""
    assert "usage:" in stderr

    exit_code, stdout, stderr = _run_cli(
        [
            "--source-db",
            str(tmp_path / "missing.sqlite"),
            "--temp-db",
            str(tmp_path / "temp.sqlite"),
            "--output-dir",
            str(tmp_path / "outputs"),
            "--signal-date",
            "2026-05-30",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--run-id",
            "smoke-run",
        ]
    )
    assert exit_code == 2
    assert stdout == ""
    assert "analysis_db not found" in stderr
