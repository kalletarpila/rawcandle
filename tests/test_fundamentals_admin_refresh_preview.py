from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin.refresh_fundamentals import (
    DISCOVERY_LIMIT,
    DISCOVERY_FIELDS,
    FINANCIAL_FIELDS,
    REFRESH_REQUEST_FIELDS,
    DiscoveryIncompleteError,
    HistoryValidationError,
    audit_publish_date_bootstrap,
    compare_ticker_histories,
    detect_fiscal_identity_revisions,
    discover_changed_tickers,
    ensure_refresh_state_schema,
    fiscal_identity,
    fetch_complete_history,
    history_fingerprints,
    normalize_source_row,
    publish_date_impact,
    publication_date_status,
    resolve_refresh_state,
    run_preview,
    semantic_row_fingerprints,
    source_key,
    validate_complete_history,
)
from rawcandle.fundamentals.admin.refresh_scheduler import (
    run_scheduler_refresh_discovery,
)
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
from rawcandle.fundamentals.providers.sharadar import AUTH_OK, STATUS_SUCCESS, SharadarResult
from rawcandle.scheduler.config import (
    create_default_scheduler_config,
    write_scheduler_config,
)
from rawcandle.scheduler.runner import (
    STATUS_OK,
    ScheduledMarketRunResult,
    run_scheduler_config,
)


def row(
    *,
    ticker: str = "TEST",
    dimension: str = "ARQ",
    filing_date: str = "2026-08-26",
    reportperiod: str = "2026-07-31",
    fiscalperiod: str = "2026-Q2",
    lastupdated: str = "2026-08-26",
    revenue: int = 100,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "ticker": ticker,
        "dimension": dimension,
        "date": filing_date,
        "reportperiod": reportperiod,
        "calendardate": reportperiod,
        "fiscalperiod": fiscalperiod,
        "lastupdated": lastupdated,
    }
    payload.update({field: None for field in FINANCIAL_FIELDS})
    payload.update({"revenue": revenue, "netinc": 10, "sharesbas": 5})
    return payload


def result(records: list[dict[str, object]], *, payload: object | None = None) -> SharadarResult:
    return SharadarResult(
        status=STATUS_SUCCESS,
        auth_status=AUTH_OK,
        http_status=200,
        endpoint="/data/fundamentals",
        url="https://api.sharadar.com/v1.0/data/fundamentals",
        request_count=1,
        records=records,
        payload=records if payload is None else payload,
    )


class DiscoveryClient:
    def __init__(self, initial: list[dict[str, object]], partition: list[dict[str, object]] | None = None) -> None:
        self.initial = initial
        self.partition = partition if partition is not None else initial
        self.calls: list[dict[str, object]] = []

    def fundamentals(self, **kwargs):
        self.calls.append(kwargs)
        filters = kwargs.get("filters") or {}
        return result(self.partition if "lastupdated" in filters else self.initial)


class PreviewClient:
    def __init__(self, source_arq: list[dict[str, object]], source_mrq: list[dict[str, object]]) -> None:
        self.source_arq = source_arq
        self.source_mrq = source_mrq

    def schema(self, _table: str):
        return result([], payload=[{"name": field} for field in REFRESH_REQUEST_FIELDS])

    def fundamentals(self, **kwargs):
        dimension = kwargs.get("dimension")
        if kwargs.get("ticker"):
            return result(self.source_arq if dimension == "ARQ" else self.source_mrq)
        updated = max(str(item["lastupdated"]) for item in self.source_arq + self.source_mrq)
        return result([{"ticker": "TEST", "dimension": dimension, "lastupdated": updated}])


def test_source_key_is_true_sharadar_key_and_stable_across_lastupdated() -> None:
    original = row()
    revised = dict(original, lastupdated="2026-09-15", revenue=120)
    assert source_key(original) == ("TEST", "ARQ", "2026-08-26", "2026-07-31")
    assert source_key(original) == source_key(revised)
    assert source_key(dict(original, date="2026-08-27")) != source_key(original)
    assert source_key(dict(original, reportperiod="2026-07-30")) != source_key(original)


def test_semantic_hashes_are_order_independent_and_separate_metadata() -> None:
    first = row()
    second = row(filing_date="2026-05-20", reportperiod="2026-04-30", fiscalperiod="2026-Q1")
    assert history_fingerprints([first, second]) == history_fingerprints([second, first])
    original = semantic_row_fingerprints(first)
    metadata = semantic_row_fingerprints(dict(first, lastupdated="2026-09-15"))
    financial = semantic_row_fingerprints(dict(first, revenue=101))
    assert original["raw_source_fingerprint"] != metadata["raw_source_fingerprint"]
    assert original["effective_content_fingerprint"] == metadata["effective_content_fingerprint"]
    assert original["effective_content_fingerprint"] != financial["effective_content_fingerprint"]
    assert normalize_source_row(dict(reversed(list(first.items())))) == normalize_source_row(first)


def test_complete_history_validation_is_structural_not_row_count_based() -> None:
    trusted = validate_complete_history([row()], ticker="TEST", dimension="ARQ")
    assert trusted.status == "COMPLETE"
    assert trusted.row_count == 1
    empty = validate_complete_history([], ticker="TEST", dimension="ARQ")
    assert empty.status == "INCOMPLETE"
    assert "EMPTY_HISTORY_RESPONSE" in empty.errors
    duplicate = validate_complete_history([row(), row(revenue=200)], ticker="TEST", dimension="ARQ")
    assert duplicate.status == "INCOMPLETE"
    assert "DUPLICATE_SOURCE_PRIMARY_KEY" in duplicate.errors
    wrong = validate_complete_history([row(ticker="OTHER")], ticker="TEST", dimension="ARQ")
    assert wrong.status == "INCOMPLETE"
    malformed = validate_complete_history([dict(row(), date="not-a-date")], ticker="TEST", dimension="ARQ")
    assert malformed.status == "INCOMPLETE"
    exact_limit = validate_complete_history([row()], ticker="TEST", dimension="ARQ", response_reached_limit=True)
    assert exact_limit.status == "INCOMPLETE"


def test_complete_history_authority_does_not_use_lossy_fields_projection() -> None:
    class ContractClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def fundamentals(self, **kwargs):
            self.calls.append(kwargs)
            return result([row(ticker=str(kwargs["ticker"]), dimension=str(kwargs["dimension"]))])

    client = ContractClient()
    trust = fetch_complete_history(client, "TEST", "ARQ")
    assert trust.status == "COMPLETE"
    assert trust.rows[0]["fiscalperiod"] == "2026-Q2"
    assert "fields" not in client.calls[0]
    assert set(REFRESH_REQUEST_FIELDS).issubset(trust.rows[0])

    discovery = DiscoveryClient([{"ticker": "TEST", "dimension": "ARQ", "lastupdated": "2026-09-15"}])
    discover_changed_tickers(discovery, query_start_date="2026-09-15", today=date(2026, 9, 15))
    assert discovery.calls[0]["fields"] == DISCOVERY_FIELDS


def test_fiscal_identity_uses_explicit_fiscalperiod() -> None:
    assert fiscal_identity("2027-Q2") == (2027, "Q2")
    with pytest.raises(HistoryValidationError, match="INVALID_FISCAL_PERIOD"):
        fiscal_identity("2026-08-31")


def test_watermark_bootstrap_and_established_state(tmp_path: Path) -> None:
    db = tmp_path / "provider.db"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE sharadar_fundamental_observation(dimension TEXT,lastupdated TEXT)")
        connection.execute("INSERT INTO sharadar_fundamental_observation VALUES('ARQ','2026-09-09')")
    bootstrap = resolve_refresh_state(db)
    assert bootstrap.mode == "BOOTSTRAP_BASELINE"
    assert bootstrap.published_watermark is None
    assert bootstrap.derived_watermark == "2026-09-09"
    assert bootstrap.query_start_date == "2026-09-06"
    with sqlite3.connect(db) as connection:
        ensure_refresh_state_schema(connection)
        connection.execute(
            "INSERT INTO sharadar_refresh_state VALUES(1,'SHARADAR','fundamentals','2026-09-15','provider','schema','run','2026-09-15T12:00:00Z')"
        )
    established = resolve_refresh_state(db)
    assert established.mode == "ESTABLISHED"
    assert established.published_watermark == "2026-09-15"
    assert established.query_start_date == "2026-09-12"


def test_discovery_uses_inclusive_overlap_filter() -> None:
    client = DiscoveryClient([{"ticker": "ABC", "dimension": "ARQ", "lastupdated": "2026-09-15"}])
    evidence = discover_changed_tickers(client, query_start_date="2026-09-12", today=date(2026, 9, 15))
    assert evidence["changed_tickers"] == ["ABC"]
    assert client.calls[0]["filters"] == {"lastupdated.gte": "2026-09-12"}


def test_discovery_partitions_exact_limit_and_fails_closed() -> None:
    ceiling = [{"ticker": "ABC", "dimension": "ARQ", "lastupdated": "2026-09-15"}] * DISCOVERY_LIMIT
    client = DiscoveryClient(ceiling, [{"ticker": "ABC", "dimension": "ARQ", "lastupdated": "2026-09-15"}])
    evidence = discover_changed_tickers(client, query_start_date="2026-09-15", today=date(2026, 9, 15))
    assert evidence["partitioned"] is True
    assert any(call["filters"] == {"lastupdated": "2026-09-15"} for call in client.calls)
    blocked = DiscoveryClient(ceiling, ceiling)
    with pytest.raises(DiscoveryIncompleteError, match="DISCOVERY_INCOMPLETE"):
        discover_changed_tickers(blocked, query_start_date="2026-09-15", today=date(2026, 9, 15))


def histories(old_arq: dict[str, object], new_arq: dict[str, object], *, old_mrq: dict[str, object] | None = None, new_mrq: dict[str, object] | None = None):
    old_mrq = old_mrq or row(dimension="MRQ")
    new_mrq = new_mrq or dict(old_mrq)
    current = {
        "ARQ": {"rows": (normalize_source_row(old_arq),), "current_row_count": 1, "legacy_versions_collapsed": 0, "invalid_rows": [], **history_fingerprints([old_arq])},
        "MRQ": {"rows": (normalize_source_row(old_mrq),), "current_row_count": 1, "legacy_versions_collapsed": 0, "invalid_rows": [], **history_fingerprints([old_mrq])},
    }
    source = {
        "ARQ": validate_complete_history([new_arq], ticker="TEST", dimension="ARQ"),
        "MRQ": validate_complete_history([new_mrq], ticker="TEST", dimension="MRQ"),
    }
    return current, source


@pytest.mark.parametrize(
    ("new_arq", "expected"),
    [
        (row(lastupdated="2026-09-15"), "SOURCE_ONLY_METADATA_CHANGE"),
        (row(revenue=120, lastupdated="2026-09-15"), "HISTORICAL_REVISION"),
        (row(), "NO_EFFECTIVE_CHANGE"),
    ],
)
def test_comparison_metadata_revision_and_no_change(new_arq: dict[str, object], expected: str) -> None:
    current, source = histories(row(), new_arq)
    assert compare_ticker_histories("TEST", current, source)["classification"] == expected


def test_same_key_fiscal_identity_revision_is_explicit_and_fail_closed() -> None:
    old = row(fiscalperiod="2026-Q1")
    current, source = histories(old, dict(old, fiscalperiod="2026-Q4", lastupdated="2026-09-15"))
    revisions = detect_fiscal_identity_revisions("TEST", current, source)
    assert len(revisions) == 1
    assert revisions[0]["event"] == "FISCAL_IDENTITY_REVISION"
    assert revisions[0]["financial_payload_changed"] is False
    result = compare_ticker_histories("TEST", current, source)
    assert result["classification"] == "REVIEW_REQUIRED"
    assert result["review_reason"] == "REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION"


def test_fiscal_and_financial_revision_are_both_reported() -> None:
    old = row(fiscalperiod="2026-Q1", revenue=100)
    current, source = histories(
        old, dict(old, fiscalperiod="2026-Q4", lastupdated="2026-09-15", revenue=200),
    )
    event = compare_ticker_histories("TEST", current, source)["fiscal_identity_revisions"][0]
    assert event["financial_payload_changed"] is True


def test_fiscal_revision_reports_duplicate_target_but_still_reviews_coherent_case() -> None:
    old = row(fiscalperiod="2026-Q1")
    target = row(filing_date="2026-05-20", reportperiod="2026-04-30", fiscalperiod="2026-Q4")
    revised = dict(old, fiscalperiod="2026-Q4", lastupdated="2026-09-15")
    current, source = histories(old, revised)
    source["ARQ"] = validate_complete_history([target, revised], ticker="TEST", dimension="ARQ")
    result = compare_ticker_histories("TEST", current, source)
    assert result["fiscal_identity_revisions"][0]["target_fiscal_identity_already_exists"] is True
    assert result["classification"] == "REVIEW_REQUIRED"


def test_fiscal_revision_preserves_independent_source_removal_evidence() -> None:
    revised_old = row(fiscalperiod="2026-Q1")
    removed_old = row(
        filing_date="2025-05-20", reportperiod="2025-04-30", fiscalperiod="2025-Q1",
    )
    current, source = histories(
        revised_old, dict(revised_old, fiscalperiod="2026-Q4", lastupdated="2026-09-15"),
    )
    current["ARQ"]["rows"] = [removed_old, revised_old]
    result = compare_ticker_histories("TEST", current, source)
    assert result["classification"] == "REVIEW_REQUIRED"
    assert result["fiscal_identity_revisions"]
    assert result["source_history_action"]["ambiguous_removals"] == 1
    assert any(
        event.get("event") == "AMBIGUOUS_SOURCE_REMOVAL"
        for event in result["source_history_events"]
    )


def test_short_oldest_boundary_removal_fails_closed_but_same_fiscal_replacement_is_removed() -> None:
    old_q1 = row(filing_date="2026-05-20", reportperiod="2026-04-30", fiscalperiod="2026-Q1")
    new_q2 = row()
    current, source = histories(old_q1, new_q2)
    result = compare_ticker_histories("TEST", current, source)
    assert result["classification"] == "REVIEW_REQUIRED"
    assert result["review_reason"] == "AMBIGUOUS_SOURCE_REMOVAL"
    current, source = histories(row(), row(filing_date="2026-08-27"))
    result = compare_ticker_histories("TEST", current, source)
    assert result["classification"] == "SOURCE_REMOVAL"
    assert result["source_history_action"]["true_source_removals"] == 1


def _create_preview_databases(root: Path) -> BatchAddTickerPaths:
    root.mkdir(parents=True, exist_ok=True)
    provider = root / "provider.db"
    canonical = root / "canonical.db"
    analysis = root / "analysis.db"
    market = root / "market.db"
    taxonomy = root / "taxonomy.db"
    with sqlite3.connect(provider) as connection:
        connection.executescript(
            """
            CREATE TABLE provider_observation(
                observation_id TEXT PRIMARY KEY, provider_record_key TEXT,
                company_id INTEGER, security_id INTEGER
            );
            CREATE TABLE sharadar_fundamental_observation(
                observation_id TEXT PRIMARY KEY, ticker TEXT, dimension TEXT,
                calendardate TEXT, reportperiod TEXT, fiscalperiod TEXT, date TEXT,
                lastupdated TEXT, revenue, gp, opinc, ebit, ebitda, netinc, ncfo,
                capex, fcf, cashneq, debt, debtc, debtnc, sharesbas, shareswa,
                shareswadil, netinccmn, receivables, inventory, payables,
                deferredrev, assets
            );
            CREATE TABLE sharadar_ticker_metadata(
                table_name TEXT,ticker TEXT,permaticker TEXT,isdelisted TEXT,
                relatedtickers TEXT,lastupdated TEXT
            );
            """
        )
        for dimension, observation in (("ARQ", "arq"), ("MRQ", "mrq")):
            item = row(dimension=dimension)
            connection.execute("INSERT INTO provider_observation VALUES(?,?,1,1)", (observation, "legacy"))
            fields = ["observation_id", *REFRESH_REQUEST_FIELDS]
            connection.execute(
                f"INSERT INTO sharadar_fundamental_observation({','.join(fields)}) VALUES({','.join('?' for _ in fields)})",
                [observation, *[item.get(field) for field in REFRESH_REQUEST_FIELDS]],
            )
        connection.execute("INSERT INTO sharadar_ticker_metadata VALUES('fundamentals','TEST','100','N',NULL,'2026-08-26')")
    with sqlite3.connect(canonical) as connection:
        connection.executescript(
            """
            CREATE TABLE security(security_id INTEGER PRIMARY KEY,company_id INTEGER,current_ticker TEXT,active INTEGER);
            CREATE TABLE ticker_alias(security_id INTEGER,ticker TEXT);
            CREATE TABLE provider_security_identity(provider TEXT,provider_security_id TEXT,security_id INTEGER,provider_ticker TEXT);
            CREATE TABLE v4_quarter(
                quarter_id INTEGER PRIMARY KEY,company_id INTEGER,fiscal_year INTEGER,
                fiscal_quarter TEXT,period_end TEXT,source_availability_date TEXT,
                first_public_result_date TEXT
            );
            INSERT INTO security VALUES(1,1,'TEST',1);
            INSERT INTO provider_security_identity VALUES('SHARADAR','100',1,'TEST');
            INSERT INTO v4_quarter VALUES(1,1,2026,'Q2','2026-07-31','2026-08-26',NULL);
            """
        )
    for path in (analysis, market, taxonomy):
        sqlite3.connect(path).close()
    return BatchAddTickerPaths(provider, canonical, analysis, market, taxonomy)


def test_publish_date_bootstrap_is_read_only_and_uses_stable_quarter_identity(tmp_path: Path) -> None:
    paths = _create_preview_databases(tmp_path)
    audit = audit_publish_date_bootstrap(paths)
    assert audit["counts"] == {
        "ALREADY_ESTABLISHED": 0, "BOOTSTRAP_ELIGIBLE": 1, "REPAIR_REQUIRED": 0,
    }
    assert audit["contract"]["stable_quarter_identity"] == ["company_id", "fiscal_year", "fiscal_quarter"]
    comparison = {
        "added_keys": [],
        "changed_keys": [{"ticker": "TEST", "dimension": "ARQ", "date": "2026-08-26", "reportperiod": "2026-07-31"}],
        "removed_keys": [],
        "affected_fiscal_quarters": [{"fiscal_year": 2026, "fiscal_quarter": "Q2"}],
    }
    impact = publish_date_impact(
        paths,
        identity={"ticker": "TEST", "company_id": 1},
        comparison=comparison,
        source_arq_rows=[row(lastupdated="2026-09-15", revenue=120)],
    )
    assert impact[0]["policy_result"] == "BOOTSTRAP_FIRST_PUBLIC_RESULT_DATE_ON_COPY"
    assert impact[0]["proposed_first_public_result_date_baseline"] == "2026-08-26"
    assert impact[0]["source_lastupdated"] == "2026-09-15"


def test_established_historical_baseline_has_zero_bootstrap_and_allows_source_difference(
    tmp_path: Path,
) -> None:
    paths = _create_preview_databases(tmp_path)
    with sqlite3.connect(paths.canonical_db) as connection:
        connection.execute(
            "UPDATE v4_quarter SET first_public_result_date='2026-08-20',"
            "source_availability_date='2026-09-15'"
        )
    audit = audit_publish_date_bootstrap(paths)
    assert audit["existing_canonical_quarters"] == 1
    assert audit["established_first_public_dates"] == 1
    assert audit["historical_bootstrap_eligible"] == 0
    assert audit["historical_preservation_applicable"] == 1
    assert audit["repair_required"] == 0
    assert audit["all_current_quarters_bootstrap_eligible"] is False
    assert audit["all_current_quarter_dates_valid"] is True


def test_publication_date_status_uses_canonical_impacts_not_source_row_counts() -> None:
    new = {
        "policy_result": "ESTABLISH_INITIAL_DATE_USING_EXISTING_CANONICAL_POLICY",
        "source_date": "2026-11-20",
    }
    preserved = {
        "policy_result": "PRESERVE_EXISTING_FIRST_PUBLIC_RESULT_DATE",
        "source_availability_date_would_drift": True,
    }
    no_impact = {"policy_result": "NO_CANONICAL_DATE_IMPACT", "source_date": None}
    assert publication_date_status([new])["status"] == "NEW_QUARTER"
    assert publication_date_status([preserved])["status"] == "PRESERVED"
    combined = publication_date_status([new, preserved])
    assert combined["status"] == "NEW_QUARTER_AND_PRESERVED_HISTORY"
    assert combined["label"] == "New quarter + preserved history"
    assert publication_date_status([no_impact])["status"] == "NO_DATE_IMPACT"


@pytest.mark.parametrize(
    ("classification", "impacts", "expected"),
    [
        (
            "NEW_QUARTER",
            [{"policy_result": "ESTABLISH_INITIAL_DATE_USING_EXISTING_CANONICAL_POLICY", "source_date": "2026-11-20"}],
            "NEW_QUARTER",
        ),
        (
            "HISTORICAL_REVISION",
            [{"policy_result": "PRESERVE_EXISTING_FIRST_PUBLIC_RESULT_DATE"}],
            "PRESERVED",
        ),
        (
            "NEW_QUARTER_AND_REVISION",
            [
                {"policy_result": "ESTABLISH_INITIAL_DATE_USING_EXISTING_CANONICAL_POLICY", "source_date": "2026-11-20"},
                {"policy_result": "PRESERVE_EXISTING_FIRST_PUBLIC_RESULT_DATE"},
            ],
            "NEW_QUARTER_AND_PRESERVED_HISTORY",
        ),
        (
            "SOURCE_REMOVAL",
            [{"policy_result": "PRESERVE_EXISTING_FIRST_PUBLIC_RESULT_DATE"}],
            "PRESERVED",
        ),
    ],
)
def test_change_classes_have_canonical_publication_date_status(
    classification: str, impacts: list[dict[str, object]], expected: str,
) -> None:
    assert classification in {
        "NEW_QUARTER", "HISTORICAL_REVISION", "NEW_QUARTER_AND_REVISION", "SOURCE_REMOVAL",
    }
    assert publication_date_status(impacts)["status"] == expected


def test_missing_canonical_quarter_without_arq_winner_has_no_date_impact(tmp_path: Path) -> None:
    paths = _create_preview_databases(tmp_path)
    impact = publish_date_impact(
        paths,
        identity={"ticker": "TEST", "company_id": 1},
        comparison={"affected_fiscal_quarters": [{"fiscal_year": 2020, "fiscal_quarter": "Q1"}]},
        source_arq_rows=[row()],
    )
    assert impact[0]["policy_result"] == "NO_CANONICAL_DATE_IMPACT"
    assert publication_date_status(impact)["label"] == "No date impact"


def test_realistic_preview_writes_artifacts_but_not_databases(tmp_path: Path) -> None:
    paths = _create_preview_databases(tmp_path / "dbs")
    before = {name: (path.stat().st_size, path.stat().st_mtime_ns) for name, path in paths.as_dict().items()}
    source_arq = [row(lastupdated="2026-09-15", revenue=120)]
    source_mrq = [row(dimension="MRQ", lastupdated="2026-09-15")]
    output = run_preview(
        source_paths=paths,
        run_root=tmp_path / "runs",
        client=PreviewClient(source_arq, source_mrq),
    )
    after = {name: (path.stat().st_size, path.stat().st_mtime_ns) for name, path in paths.as_dict().items()}
    assert before == after
    assert output["outcome"] == "COMPLETED", output
    assert output["summary_counts"]["HISTORICAL_REVISION"] == 1
    assert output["refresh_preview"]["state"]["mode"] == "BOOTSTRAP_BASELINE"
    assert output["refresh_preview"]["published_watermark_advanced"] is False
    run_dir = Path(output["artifact_dir"])
    for name in (
        "refresh_preview.json",
        "refresh_ticker_changes.json",
        "refresh_unknown_tickers.json",
        "refresh_review_required.json",
        "operation_report.md",
        "progress_events.jsonl",
        "result.json",
    ):
        assert (run_dir / name).is_file()
    preview = json.loads((run_dir / "refresh_preview.json").read_text(encoding="utf-8"))
    assert preview["refresh_set_fingerprint"] == output["preview_fingerprint"]


def test_scheduler_dispatch_uses_real_read_only_preview_with_fake_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _create_preview_databases(tmp_path / "dbs")
    run_root = tmp_path / "runs"
    with sqlite3.connect(paths.provider_db) as connection:
        ensure_refresh_state_schema(connection)
        connection.execute(
            "INSERT INTO sharadar_refresh_state VALUES(1,'SHARADAR','fundamentals',"
            "'2026-08-26','provider','schema','published-run','2026-08-26T12:00:00Z')"
        )
    with sqlite3.connect(paths.provider_db) as connection:
        baseline_state = connection.execute(
            "SELECT published_source_watermark,successful_run_id FROM sharadar_refresh_state"
        ).fetchone()
    before = {
        name: (path.stat().st_size, path.stat().st_mtime_ns)
        for name, path in paths.as_dict().items()
    }
    client = PreviewClient(
        [row(lastupdated="2026-09-15", revenue=120)],
        [row(dimension="MRQ", lastupdated="2026-09-15")],
    )
    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.refresh_scheduler.safety_status",
        lambda: {"status": "CLEAR", "production_writes_blocked": False},
    )

    def real_preview(**kwargs):
        return run_preview(source_paths=paths, client=client, **kwargs)

    discoveries = []
    original_discovery = run_scheduler_refresh_discovery

    def fixture_discovery():
        output = original_discovery(
            run_root=run_root,
            operation_lock_path=tmp_path / "operation.lock",
            preview_backend=real_preview,
        )
        discoveries.append(output)
        return output

    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.refresh_scheduler."
        "run_scheduler_refresh_discovery",
        fixture_discovery,
    )
    config = create_default_scheduler_config(
        osakedata_db_path=str(paths.market_db),
        analysis_db_path=str(paths.taxonomy_db),
        log_dir=str(tmp_path / "logs"),
    )
    config.enabled_markets = ["omxh"]
    config.fundamentals_refresh_preview_enabled = True
    config_path = tmp_path / "scheduler.json"
    write_scheduler_config(str(config_path), config)
    monkeypatch.setattr(
        "rawcandle.scheduler.runner._run_one_market",
        lambda **_kwargs: ScheduledMarketRunResult(
            market="omxh",
            started_at_utc="2026-09-22T01:00:00Z",
            finished_at_utc="2026-09-22T01:00:01Z",
            exit_code=0,
            summary_status=STATUS_OK,
            log_path=str(tmp_path / "logs" / "market.log"),
            summary_lines=[],
        ),
    )

    scheduler_result = run_scheduler_config(config_path=str(config_path))
    output = discoveries[0]

    after = {
        name: (path.stat().st_size, path.stat().st_mtime_ns)
        for name, path in paths.as_dict().items()
    }
    with sqlite3.connect(paths.provider_db) as connection:
        final_state = connection.execute(
            "SELECT published_source_watermark,successful_run_id FROM sharadar_refresh_state"
        ).fetchone()
    assert output["scheduler_summary_result"] == "CHANGES_FOUND"
    assert output["pending_changes"] is True
    assert output["review_required"] is False
    assert output["test_invoked"] is False
    assert output["production_invoked"] is False
    assert output["full_workflow_invoked"] is False
    assert output["published_baseline"] == "2026-08-26"
    assert scheduler_result.fundamentals_refresh_preview_status == "CHANGES_FOUND"
    assert scheduler_result.fundamentals_refresh_pending_changes is True
    summary = json.loads(
        Path(scheduler_result.summary_json_path).read_text(encoding="utf-8")
    )
    assert summary["fundamentals_refresh_preview_run_id"] == output["run_id"]
    assert summary["fundamentals_refresh_preview_report"] == output["report"]
    assert baseline_state == final_state == ("2026-08-26", "published-run")
    assert before == after
    assert Path(str(output["report"])).is_file()
    assert not list(tmp_path.rglob("*_candidate.db"))


def test_established_revision_report_is_preserved_and_has_current_contract_wording(
    tmp_path: Path,
) -> None:
    paths = _create_preview_databases(tmp_path / "dbs")
    with sqlite3.connect(paths.canonical_db) as connection:
        connection.execute("UPDATE v4_quarter SET first_public_result_date='2026-08-26'")
    output = run_preview(
        source_paths=paths,
        run_root=tmp_path / "runs",
        client=PreviewClient(
            [row(lastupdated="2026-09-15", revenue=120)],
            [row(dimension="MRQ", lastupdated="2026-09-15")],
        ),
    )
    change = output["refresh_preview"]["ticker_changes"][0]
    assert change["classification"] == "HISTORICAL_REVISION"
    assert change["publication_date_status"]["status"] == "PRESERVED"
    state = output["refresh_preview"]["publication_date_state"]
    assert state["established_first_public_dates"] == 1
    assert state["historical_bootstrap_eligible"] == 0
    assert state["repair_required"] == 0
    report = (Path(output["artifact_dir"]) / "operation_report.md").read_text(encoding="utf-8")
    assert "| Preserved |" in report
    assert "will be bootstrapped on copies" not in report
    assert "historical `first_public_result_date` baseline is established in production" in report


def test_next_preview_after_published_generation_is_no_change(tmp_path: Path) -> None:
    paths = _create_preview_databases(tmp_path / "dbs")
    with sqlite3.connect(paths.provider_db) as connection:
        ensure_refresh_state_schema(connection)
        connection.execute(
            "INSERT INTO sharadar_refresh_state VALUES(1,'SHARADAR','fundamentals',"
            "'2026-08-26','provider','schema','published-run','2026-08-26T12:00:00Z')"
        )
    source_arq = [row()]
    source_mrq = [row(dimension="MRQ")]
    output = run_preview(
        source_paths=paths,
        run_root=tmp_path / "runs",
        client=PreviewClient(source_arq, source_mrq),
    )
    assert output["outcome"] == "NO_CHANGE"
    assert output["summary_counts"]["effective_changed_known"] == 0
    assert output["refresh_preview"]["state"]["mode"] == "ESTABLISHED"
    assert output["refresh_preview"]["state"]["published_watermark"] == "2026-08-26"
    assert output["refresh_preview"]["future_test_authorized"] is False


def test_consecutive_scheduler_previews_keep_published_baseline_and_accumulate_pending_source(
    tmp_path: Path,
) -> None:
    paths = _create_preview_databases(tmp_path / "dbs")
    with sqlite3.connect(paths.provider_db) as connection:
        ensure_refresh_state_schema(connection)
        connection.execute(
            "INSERT INTO sharadar_refresh_state VALUES(1,'SHARADAR','fundamentals',"
            "'2026-08-26','provider','schema','published-run','2026-08-26T12:00:00Z')"
        )
    revised_q2 = row(lastupdated="2026-09-15", revenue=120)
    first = run_preview(
        source_paths=paths,
        run_root=tmp_path / "runs-first",
        client=PreviewClient([revised_q2], [row(dimension="MRQ", lastupdated="2026-09-15")]),
        trigger_source="SCHEDULER",
    )
    new_q3 = row(
        filing_date="2026-11-20", reportperiod="2026-10-31",
        fiscalperiod="2026-Q3", lastupdated="2026-11-20", revenue=130,
    )
    second = run_preview(
        source_paths=paths,
        run_root=tmp_path / "runs-second",
        client=PreviewClient(
            [revised_q2, new_q3],
            [
                row(dimension="MRQ", lastupdated="2026-09-15"),
                dict(new_q3, dimension="MRQ"),
            ],
        ),
        trigger_source="SCHEDULER",
    )
    assert first["refresh_preview"]["state"]["published_watermark"] == "2026-08-26"
    assert second["refresh_preview"]["state"]["published_watermark"] == "2026-08-26"
    assert first["summary_counts"]["HISTORICAL_REVISION"] == 1
    assert second["summary_counts"]["NEW_QUARTER_AND_REVISION"] == 1
    second_change = second["refresh_preview"]["ticker_changes"][0]
    assert second_change["changed_count"] >= 1
    assert second_change["added_count"] >= 1
    with sqlite3.connect(paths.provider_db) as connection:
        state = connection.execute(
            "SELECT published_source_watermark,successful_run_id FROM sharadar_refresh_state"
        ).fetchone()
    assert state == ("2026-08-26", "published-run")
    assert first["trigger_source"] == second["trigger_source"] == "SCHEDULER"
    assert first["refresh_preview"]["future_test_authorized"] is False
    assert second["refresh_preview"]["future_test_authorized"] is False
    second_report = (Path(second["artifact_dir"]) / "operation_report.md").read_text(encoding="utf-8")
    assert "Publication-Date State" in second_report
    assert "will be bootstrapped on copies" not in second_report


def test_routine_refresh_never_overrides_established_first_public_date(tmp_path: Path) -> None:
    paths = _create_preview_databases(tmp_path)
    with sqlite3.connect(paths.canonical_db) as connection:
        connection.execute("UPDATE v4_quarter SET first_public_result_date='2026-08-26'")
    comparison = {
        "added_keys": [],
        "changed_keys": [{"ticker": "TEST", "dimension": "ARQ", "date": "2026-09-15", "reportperiod": "2026-07-31"}],
        "removed_keys": [],
        "affected_fiscal_quarters": [{"fiscal_year": 2026, "fiscal_quarter": "Q2"}],
    }
    impact = publish_date_impact(
        paths,
        identity={"ticker": "TEST", "company_id": 1},
        comparison=comparison,
        source_arq_rows=[row(filing_date="2026-09-15", lastupdated="2026-09-15", revenue=120)],
    )
    assert impact[0]["policy_result"] == "PRESERVE_EXISTING_FIRST_PUBLIC_RESULT_DATE"
    assert impact[0]["proposed_first_public_result_date_baseline"] == "2026-08-26"


def test_ui_service_exposes_refresh_preview_copy_test_and_production(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []
    apply_calls: list[dict[str, object]] = []

    def preview(**kwargs):
        calls.append(kwargs)
        return {
            "operation_type": "REFRESH_FUNDAMENTALS",
            "outcome": "NO_CHANGE",
            "mode": "PREVIEW",
            "summary_counts": {"effective_changed_known": 0},
        }

    def apply(**kwargs):
        apply_calls.append(kwargs)
        return {
            "operation_type": "REFRESH_FUNDAMENTALS",
            "outcome": "COMPLETED",
            "mode": "COPY_ONLY_APPLY",
            "preview_fingerprint": "f" * 64,
        }

    service = FundamentalsAdminUIService(run_root=tmp_path, refresh_preview=preview, refresh_apply=apply)
    capability = next(item for item in service.capabilities() if item.operation_type == "REFRESH_FUNDAMENTALS")
    assert capability.preview_enabled is True
    assert capability.copy_apply_enabled is True
    assert capability.production_apply_enabled is True
    assert capability.production_confirmation_hint == "CONFIRM_PRODUCTION_REFRESH_FUNDAMENTALS"
    response = service.preview("REFRESH_FUNDAMENTALS")
    assert response.outcome == "NO_CHANGE"
    assert len(calls) == 1
    tested = service.copy_apply(
        "REFRESH_FUNDAMENTALS",
        preview_payload_path=str(tmp_path / "preview.json"),
        preview_fingerprint="f" * 64,
    )
    assert tested.outcome == "COMPLETED"
    assert apply_calls[0]["confirm_apply"] is True
