from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import os
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException

from dev_tools.fundamentals_snapshot_page import (
    FUNDAMENTALS_ROUTE,
    build_fundamentals_page,
    report_download_url,
)
from dev_tools.stock_update_scheduler_ui import add_fundamentals_download_route
from rawcandle.fundamentals.snapshot.assembler import SnapshotPaths
from rawcandle.fundamentals.snapshot.ui_service import (
    FUNDAMENTAL_REPORTS_DIR,
    MAX_BATCH_TICKERS,
    PRODUCTION_SNAPSHOT_PATHS,
    FundamentalsBatchResult,
    FundamentalsBatchSummary,
    FundamentalsSnapshotUIService,
    FundamentalsUIResult,
    list_recent_fundamentals_reports,
    normalize_report_date,
    normalize_ticker,
    parse_ticker_inputs,
    resolve_report_download,
    validate_report_filename,
)
from rawcandle.fundamentals.snapshot.writer import publish_report


class _Page:
    def __init__(self) -> None:
        self.update_count = 0
        self.launched_urls = []

    def update(self) -> None:
        self.update_count += 1

    def launch_url(self, url: str) -> None:
        self.launched_urls.append(url)


def _paths(tmp_path: Path) -> SnapshotPaths:
    return SnapshotPaths(*(tmp_path / name for name in ("canonical", "analysis", "market", "taxonomy", "provider")))


def _generator(payload: str = "report\n"):
    def generate(paths, *, ticker, report_date, output_dir, overwrite):
        published = publish_report(
            output_dir=output_dir,
            ticker=ticker,
            report_date=report_date,
            markdown=payload,
            overwrite=overwrite,
        )
        return {
            "status": published.status,
            "output_path": str(published.path),
            "report_content_fingerprint": "a" * 64,
            "snapshot": {"identity": {"ticker": ticker}},
        }

    return generate


@pytest.mark.parametrize(
    ("raw", "expected"),
    ((" nvda ", "NVDA"), ("brk.b", "BRK.B"), ("rds-a", "RDS-A")),
)
def test_ticker_normalization_supports_snapshot_contract(raw: str, expected: str) -> None:
    assert normalize_ticker(raw) == expected


@pytest.mark.parametrize("raw", (None, "", "../NVDA", "NVDA;touch /tmp/x", ".BAD"))
def test_ticker_validation_rejects_missing_or_unsafe_values(raw: str | None) -> None:
    with pytest.raises(ValueError):
        normalize_ticker(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    (
        ("NVDA", ["NVDA"]),
        ("NVDA, VRT, CRMD", ["NVDA", "VRT", "CRMD"]),
        ("NVDA VRT CRMD", ["NVDA", "VRT", "CRMD"]),
        ("NVDA,VRT CRMD", ["NVDA", "VRT", "CRMD"]),
        ("NVDA\nVRT\nCRMD", ["NVDA", "VRT", "CRMD"]),
        ("  nvda,,  vrt, NVDA  crmd  ", ["NVDA", "VRT", "CRMD"]),
        ("NVDA, INVALID!, VRT", ["NVDA", "INVALID!", "VRT"]),
    ),
)
def test_multi_ticker_parser_contract(raw: str, expected: list[str]) -> None:
    assert parse_ticker_inputs(raw) == expected


@pytest.mark.parametrize("raw", (None, "", "   ", ", ,\n,"))
def test_multi_ticker_parser_rejects_empty_input(raw: str | None) -> None:
    with pytest.raises(ValueError, match="TICKERS_REQUIRED"):
        parse_ticker_inputs(raw)


def test_multi_ticker_parser_rejects_more_than_limit_without_truncation() -> None:
    raw = " ".join(f"T{i}" for i in range(MAX_BATCH_TICKERS + 1))
    with pytest.raises(ValueError, match="TOO_MANY_TICKERS"):
        parse_ticker_inputs(raw)


@pytest.mark.parametrize("raw", (None, "", "2026-02-30", "06-09-2026", "2026-9-6"))
def test_report_date_validation_rejects_missing_malformed_or_impossible_values(raw: str | None) -> None:
    with pytest.raises(ValueError):
        normalize_report_date(raw)


def test_service_generation_created_no_change_and_explicit_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "reports"
    first_service = FundamentalsSnapshotUIService(
        paths=_paths(tmp_path), output_dir=output, generator=_generator("first\n")
    )

    created = first_service.generate(
        ticker_input=" nvda ", report_date_input="2026-09-06"
    )
    unchanged = first_service.generate(
        ticker_input="nvda", report_date_input="2026-09-06"
    )
    different_service = FundamentalsSnapshotUIService(
        paths=_paths(tmp_path), output_dir=output, generator=_generator("second\n")
    )
    blocked = different_service.generate(
        ticker_input="NVDA", report_date_input="2026-09-06"
    )
    overwritten = different_service.generate(
        ticker_input="NVDA", report_date_input="2026-09-06", overwrite=True
    )

    assert (created.status, created.publication_status) == ("GENERATED", "CREATED")
    assert (unchanged.status, unchanged.publication_status) == ("NO_CHANGE", "NO_CHANGE")
    assert blocked.status == "OVERWRITE_REQUIRED"
    assert (overwritten.status, overwritten.publication_status) == ("GENERATED", "OVERWRITTEN")
    assert overwritten.filename == "NVDA_2026-09-06.md"
    assert (output / overwritten.filename).read_text() == "second\n"
    assert len(list(output.iterdir())) == 1


def test_batch_partial_success_order_summary_and_repeat(tmp_path: Path) -> None:
    output = tmp_path / "reports"

    def generator(paths, *, ticker, report_date, output_dir, overwrite):
        if ticker == "MISSING":
            raise LookupError("unknown")
        if ticker == "EARLY":
            raise RuntimeError("NOT_READY")
        if ticker == "BROKEN":
            raise RuntimeError("secret failure")
        return _generator(f"{ticker}\n")(
            paths,
            ticker=ticker,
            report_date=report_date,
            output_dir=output_dir,
            overwrite=overwrite,
        )

    service = FundamentalsSnapshotUIService(
        paths=_paths(tmp_path), output_dir=output, generator=generator
    )
    raw = "good, INVALID! missing EARLY broken GOOD other"
    first = service.generate_batch(
        ticker_input=raw, report_date_input="2026-09-06"
    )
    second = service.generate_batch(
        ticker_input=raw, report_date_input="2026-09-06"
    )

    assert [result.ticker for result in first.results] == [
        "GOOD", "INVALID!", "MISSING", "EARLY", "BROKEN", "OTHER"
    ]
    assert [result.status for result in first.results] == [
        "GENERATED", "INVALID_TICKER", "INVALID_TICKER", "NOT_READY", "FAILED", "GENERATED"
    ]
    assert first.summary == FundamentalsBatchSummary(6, 2, 0, 0, 4)
    assert second.summary == FundamentalsBatchSummary(6, 0, 0, 2, 4)
    assert [result.publication_status for result in second.results] == [
        "NO_CHANGE", None, None, None, None, "NO_CHANGE"
    ]


def test_batch_overwrite_required_does_not_block_later_ticker(tmp_path: Path) -> None:
    output = tmp_path / "reports"
    original = FundamentalsSnapshotUIService(
        paths=_paths(tmp_path), output_dir=output, generator=_generator("old\n")
    )
    original.generate(ticker_input="ONE", report_date_input="2026-09-06")
    changed = FundamentalsSnapshotUIService(
        paths=_paths(tmp_path), output_dir=output, generator=_generator("new\n")
    )

    blocked = changed.generate_batch(
        ticker_input="ONE TWO", report_date_input="2026-09-06"
    )
    overwritten = changed.generate_batch(
        ticker_input="ONE TWO", report_date_input="2026-09-06", overwrite=True
    )

    assert [result.status for result in blocked.results] == [
        "OVERWRITE_REQUIRED", "GENERATED"
    ]
    assert blocked.summary == FundamentalsBatchSummary(2, 1, 0, 0, 1)
    assert [result.publication_status for result in overwritten.results] == [
        "OVERWRITTEN", "NO_CHANGE"
    ]
    assert overwritten.summary == FundamentalsBatchSummary(2, 0, 1, 1, 0)


def test_batch_rejects_global_invalid_date_and_oversized_request(tmp_path: Path) -> None:
    service = FundamentalsSnapshotUIService(
        paths=_paths(tmp_path), output_dir=tmp_path / "reports", generator=_generator()
    )
    invalid_date = service.generate_batch(
        ticker_input="ONE TWO", report_date_input="2026-02-30"
    )
    oversized = service.generate_batch(
        ticker_input=" ".join(f"T{i}" for i in range(MAX_BATCH_TICKERS + 1)),
        report_date_input="2026-09-06",
    )

    assert invalid_date.status == "INVALID_DATE"
    assert invalid_date.results == ()
    assert invalid_date.summary == FundamentalsBatchSummary(2, 0, 0, 0, 2)
    assert oversized.status == "INVALID_REQUEST"
    assert oversized.results == ()
    assert str(MAX_BATCH_TICKERS) in oversized.message


def test_service_maps_unresolved_not_ready_and_failure_without_exposing_details(tmp_path: Path) -> None:
    def unresolved(*args, **kwargs):
        raise LookupError("UNKNOWN_TICKER:SECRET")

    def not_ready(*args, **kwargs):
        raise RuntimeError("NO_CANONICAL_TTM_ENDPOINT")

    def failed(*args, **kwargs):
        raise RuntimeError("database=/secret/path token=secret")

    results = [
        FundamentalsSnapshotUIService(paths=_paths(tmp_path), output_dir=tmp_path / "a", generator=generator).generate(
            ticker_input="TEST", report_date_input="2026-09-06"
        )
        for generator in (unresolved, not_ready, failed)
    ]

    assert [result.status for result in results] == ["INVALID_TICKER", "NOT_READY", "FAILED"]
    assert "secret" not in results[-1].message.lower()


def test_service_rejects_generator_output_outside_fixed_directory(tmp_path: Path) -> None:
    def escaping(*args, **kwargs):
        return {
            "status": "CREATED",
            "output_path": str(tmp_path / "outside.md"),
            "report_content_fingerprint": "b" * 64,
            "snapshot": {"identity": {"ticker": "TEST"}},
        }

    result = FundamentalsSnapshotUIService(
        paths=_paths(tmp_path), output_dir=tmp_path / "reports", generator=escaping
    ).generate(ticker_input="TEST", report_date_input="2026-09-06")

    assert result.status == "FAILED"


def test_service_fails_closed_on_unknown_publication_status(tmp_path: Path) -> None:
    def unknown(*args, **kwargs):
        output = tmp_path / "reports" / "TEST_2026-09-06.md"
        output.parent.mkdir()
        output.write_text("report")
        return {
            "status": "MYSTERY",
            "output_path": str(output),
            "report_content_fingerprint": "b" * 64,
            "snapshot": {"identity": {"ticker": "TEST"}},
        }

    result = FundamentalsSnapshotUIService(
        paths=_paths(tmp_path), output_dir=tmp_path / "reports", generator=unknown
    ).generate(ticker_input="TEST", report_date_input="2026-09-06")

    assert result.status == "FAILED"


def test_identical_concurrent_requests_converge_to_one_complete_report(tmp_path: Path) -> None:
    service = FundamentalsSnapshotUIService(
        paths=_paths(tmp_path), output_dir=tmp_path / "reports", generator=_generator()
    )

    def generate() -> FundamentalsUIResult:
        return service.generate(ticker_input="TEST", report_date_input="2026-09-06")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: generate(), range(2)))

    assert all(result.status in {"GENERATED", "NO_CHANGE"} for result in results)
    reports = list((tmp_path / "reports").iterdir())
    assert [path.name for path in reports] == ["TEST_2026-09-06.md"]
    assert reports[0].read_text() == "report\n"


def test_recent_reports_filters_and_orders_safe_regular_contract_files(tmp_path: Path) -> None:
    valid_old = tmp_path / "NVDA_2026-09-05.md"
    valid_new = tmp_path / "BRK.B_2026-09-06.md"
    valid_old.write_text("old")
    valid_new.write_text("new")
    os.utime(valid_old, ns=(1_000_000_000, 1_000_000_000))
    os.utime(valid_new, ns=(2_000_000_000, 2_000_000_000))
    (tmp_path / "bad.md").write_text("bad")
    (tmp_path / "NVDA_2026-02-30.md").write_text("bad date")
    (tmp_path / "UNRELATED_2026-09-06.txt").write_text("other")
    (tmp_path / "DIR_2026-09-06.md").mkdir()
    try:
        (tmp_path / "LINK_2026-09-06.md").symlink_to(valid_new)
    except OSError:
        pass

    reports = list_recent_fundamentals_reports(tmp_path)

    assert {report.filename for report in reports} == {
        "NVDA_2026-09-05.md",
        "BRK.B_2026-09-06.md",
    }
    assert [report.filename for report in reports] == [
        "BRK.B_2026-09-06.md",
        "NVDA_2026-09-05.md",
    ]
    assert all(report.modified_at_utc.endswith("+00:00") for report in reports)


@pytest.mark.parametrize(
    "filename",
    (
        "bad.md",
        "NVDA_2026-02-30.md",
        "../NVDA_2026-09-06.md",
        "/tmp/NVDA_2026-09-06.md",
        "nested/NVDA_2026-09-06.md",
        "nested\\NVDA_2026-09-06.md",
        "%2e%2e%2fNVDA_2026-09-06.md",
        "NVDA_2026-09-06.md%00",
        "NVDA_2026-09-06.txt",
    ),
)
def test_report_filename_validation_rejects_unsafe_or_unrelated_names(filename: str) -> None:
    with pytest.raises(ValueError):
        validate_report_filename(filename)


def test_download_resolver_accepts_regular_contract_file_only(tmp_path: Path) -> None:
    report = tmp_path / "NVDA_2026-09-06.md"
    report.write_bytes(b"exact markdown\n")
    assert resolve_report_download(report.name, tmp_path) == report.resolve()
    with pytest.raises(FileNotFoundError):
        resolve_report_download("VRT_2026-09-06.md", tmp_path)

    directory = tmp_path / "DIR_2026-09-06.md"
    directory.mkdir()
    with pytest.raises(FileNotFoundError):
        resolve_report_download(directory.name, tmp_path)
    try:
        link = tmp_path / "LINK_2026-09-06.md"
        link.symlink_to(report)
    except OSError:
        return
    with pytest.raises(FileNotFoundError):
        resolve_report_download(link.name, tmp_path)


def test_download_route_serves_exact_bytes_as_named_attachment(tmp_path: Path) -> None:
    report = tmp_path / "BRK.B_2026-09-06.md"
    payload = b"# Exact report\n"
    report.write_bytes(payload)
    app = FastAPI()
    add_fundamentals_download_route(app, report_dir=tmp_path)
    route = next(
        route for route in app.routes
        if getattr(route, "path", None) == "/fundamentals/reports/{filename:path}"
    )

    response = asyncio.run(route.endpoint(report.name))

    assert Path(response.path).read_bytes() == payload
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == 'attachment; filename="BRK.B_2026-09-06.md"'
    for invalid in (
        "NVDA_2026-09-06.md",
        "not-a-report.md",
        "../secret.md",
        "%2e%2e%2fsecret.md",
    ):
        with pytest.raises(HTTPException) as error:
            asyncio.run(route.endpoint(invalid))
        assert error.value.status_code == 404
        assert str(tmp_path) not in str(error.value.detail)


def test_flet_page_defaults_and_normalizes_submission() -> None:
    class Service:
        def __init__(self) -> None:
            self.calls = []

        def recent_reports(self, *, limit):
            return []

        def generate_batch(self, **kwargs):
            self.calls.append(kwargs)
            assert controls.generate_button.disabled is True
            result = FundamentalsUIResult(
                status="GENERATED", message="Report generated.", ticker="NVDA",
                report_date="2026-09-06",
                filename="NVDA_2026-09-06.md",
                output_path=str(FUNDAMENTAL_REPORTS_DIR / "NVDA_2026-09-06.md"),
                report_content_fingerprint="c" * 64,
                publication_status="CREATED",
            )
            return FundamentalsBatchResult(
                status="COMPLETED", message="All tickers were attempted independently.",
                report_date="2026-09-06", results=(result,),
                summary=FundamentalsBatchSummary(1, 1, 0, 0, 0),
            )

    page = _Page()
    service = Service()
    controls = build_fundamentals_page(
        page=page, timezone_name="Europe/Helsinki", service=service
    )
    controls.ticker_field.value = " nvda "
    controls.report_date_field.value = "2026-09-06"

    controls.generate_button.on_click(None)

    assert controls.overwrite_checkbox.value is False
    assert service.calls == [{
        "ticker_input": " nvda ",
        "report_date_input": "2026-09-06",
        "overwrite": False,
    }]
    assert "Status: COMPLETED" in controls.status_field.value
    assert "Requested: 1" in controls.status_field.value
    assert controls.batch_results_column.controls[0].controls[1].value == "CREATED"
    controls.batch_results_column.controls[0].controls[-1].on_click(None)
    assert page.launched_urls == ["/fundamentals/reports/NVDA_2026-09-06.md"]
    assert controls.generate_button.disabled is False
    assert page.update_count == 2
    assert date.fromisoformat(controls.report_date_field.value)


def test_recent_report_row_has_download_action() -> None:
    from rawcandle.fundamentals.snapshot.ui_service import RecentFundamentalsReport

    class Service:
        def recent_reports(self, *, limit):
            assert limit == 10
            return [RecentFundamentalsReport(
                ticker="NVDA",
                report_date="2026-09-06",
                filename="NVDA_2026-09-06.md",
                modified_at_utc="2026-09-06T12:00:00+00:00",
            )]

    page = _Page()
    controls = build_fundamentals_page(
        page=page, timezone_name="Europe/Helsinki", service=Service()
    )
    controls.recent_reports_column.controls[0].controls[-1].on_click(None)

    assert page.launched_urls == ["/fundamentals/reports/NVDA_2026-09-06.md"]


@pytest.mark.integration
@pytest.mark.database
def test_ui_service_real_snapshot_integration_is_read_only(tmp_path: Path) -> None:
    if not all(path.is_file() for path in PRODUCTION_SNAPSHOT_PATHS.__dict__.values()):
        pytest.skip("Fundamentals V4 production databases are not present")
    service = FundamentalsSnapshotUIService(output_dir=tmp_path)

    result = service.generate(
        ticker_input="CRMD", report_date_input="2026-09-06", overwrite=False
    )

    assert result.status == "GENERATED"
    assert result.publication_status == "CREATED"
    assert result.filename == "CRMD_2026-09-06.md"
    assert (tmp_path / result.filename).is_file()
    assert len(result.report_content_fingerprint or "") == 64
    assert FUNDAMENTALS_ROUTE == "/fundamentals"
