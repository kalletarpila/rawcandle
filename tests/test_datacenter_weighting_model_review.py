from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from rawcandle.cli import run_datacenter_weighting_model_review as cli
from rawcandle.datacenter_weighting_model_review import (
    classify_constituent_breadth,
    classify_effective_member_count,
    classify_group_concentration,
    classify_largest_member_weight,
    classify_top3_share,
    guardrail_date_usable,
    run_model_review,
)


def _concentration_rows(
    *,
    count: int = 10,
    eligible: int = 4,
    effective: float = 3.0,
    largest: float = 0.3,
):
    return [
        {
            "eligible_positive_weight_member_count": eligible,
            "effective_member_count": effective,
            "largest_normalized_weight": largest,
        }
        for _ in range(count)
    ]


def test_group_concentration_classes():
    assert classify_group_concentration(_concentration_rows()) == "HEALTHY_WEIGHTED_GROUP"
    assert classify_group_concentration(
        _concentration_rows(eligible=2, effective=1.5, largest=0.6)
    ) == "CONCENTRATED_BUT_USABLE"
    assert classify_group_concentration(
        _concentration_rows(eligible=1, effective=1.0, largest=1.0)
    ) == "STRUCTURALLY_THIN"
    mostly_empty = _concentration_rows(eligible=0, effective=0.0, largest=0.0)
    mostly_empty[-1] = {
        "eligible_positive_weight_member_count": 1,
        "effective_member_count": 1.0,
        "largest_normalized_weight": 1.0,
    }
    assert classify_group_concentration(mostly_empty) == "NO_EFFECTIVE_COVERAGE"


def test_group_single_member_share_boundaries():
    healthy_boundary = _concentration_rows(count=10)
    healthy_boundary[0] = {
        "eligible_positive_weight_member_count": 1,
        "effective_member_count": 1.0,
        "largest_normalized_weight": 1.0,
    }
    assert classify_group_concentration(healthy_boundary) == "HEALTHY_WEIGHTED_GROUP"

    usable_boundary = _concentration_rows(
        count=20, eligible=2, effective=2.0, largest=0.5
    )
    for index in range(5):
        usable_boundary[index] = {
            "eligible_positive_weight_member_count": 1,
            "effective_member_count": 1.0,
            "largest_normalized_weight": 1.0,
        }
    assert classify_group_concentration(usable_boundary) == "CONCENTRATED_BUT_USABLE"
    usable_boundary[5] = usable_boundary[0]
    assert classify_group_concentration(usable_boundary) == "STRUCTURALLY_THIN"


def test_diagnostic_threshold_boundaries():
    assert [classify_constituent_breadth(value) for value in (4, 3, 2, 1, 0)] == [
        "HEALTHY", "THIN", "THIN", "SINGLE_MEMBER", "NO_EFFECTIVE_MEMBERS"
    ]
    assert classify_effective_member_count(3.0) == "HEALTHY"
    assert classify_effective_member_count(1.5) == "CONCENTRATED"
    assert classify_effective_member_count(1.499) == "HIGHLY_CONCENTRATED"
    assert classify_largest_member_weight(0.40) == "HEALTHY"
    assert classify_largest_member_weight(0.60) == "ELEVATED"
    assert classify_largest_member_weight(0.601) == "DOMINANT"
    assert classify_top3_share(0.80) == "HEALTHY"
    assert classify_top3_share(0.95) == "ELEVATED"
    assert classify_top3_share(0.951) == "EXTREME"


@pytest.mark.parametrize(
    ("candidate", "eligible", "effective", "expected"),
    [
        ("A", 0, 0.0, True),
        ("B", 1, 3.0, False),
        ("B", 2, 1.0, True),
        ("C", 5, 1.49, False),
        ("C", 2, 1.5, True),
        ("D", 1, 2.0, False),
        ("D", 2, 1.49, False),
        ("D", 2, 1.5, True),
    ],
)
def test_guardrail_candidate_filtering(candidate, eligible, effective, expected):
    assert guardrail_date_usable(
        candidate,
        eligible_positive_weight_member_count=eligible,
        effective_member_count=effective,
    ) is expected


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_model_review_is_deterministic_and_does_not_mutate_phase3_rows(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    phase3 = tmp_path / "phase3"
    phase3.mkdir()
    (phase3 / "summary.json").write_text(
        json.dumps(
            {
                "status": "OK",
                "comparison_start_date": "2024-01-02",
                "comparison_end_date": "2024-01-04",
            }
        ),
        encoding="utf-8",
    )
    comparisons = [
        {
            "group_type": "layer",
            "group_name": "Power",
            "date": f"2024-01-0{day}",
            "weighted_trend_classification": "NEUTRAL",
        }
        for day in (2, 3, 4)
    ]
    _write_csv(phase3 / "group_date_structure_comparison.csv", comparisons)
    group_summary = [{
        "group_type": "layer",
        "group_name": "Power",
        "structure_label_change_count": 1,
        "trend_classification_change_count": 1,
        "bos_matched_count": 1,
        "bos_equal_only_count": 0,
        "bos_weighted_only_count": 0,
        "median_matched_bos_timing_shift": 0,
        "max_absolute_matched_bos_timing_shift": 0,
        "reset_matched_count": 0,
        "reset_equal_only_count": 0,
        "reset_weighted_only_count": 0,
        "reset_reason_changed_count": 0,
        "median_matched_reset_timing_shift": "",
        "max_absolute_close_delta_pct": 0.1,
        "median_absolute_close_delta_pct": 0.05,
        "highest_material_change_class": "STRUCTURE_LABEL_CHANGE",
        "mechanical_causes": "SECONDARY_MEMBER_DEEMPHASIS",
    }]
    _write_csv(phase3 / "group_summary.csv", group_summary)
    _write_csv(phase3 / "largest_changes.csv", group_summary)
    _write_csv(
        phase3 / "event_comparison.csv",
        [{
            "group_type": "layer",
            "group_name": "Power",
            "event_family": "BOS",
            "status": "MATCHED",
            "weighted_event_date": "2024-01-03",
        }],
    )
    taxonomy = tmp_path / "taxonomy.csv"
    taxonomy.write_text(
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,BBB,Power,UPS,CORE,0,1.0,
""",
        encoding="utf-8",
    )
    prices = tmp_path / "prices.db"
    with sqlite3.connect(prices) as connection:
        connection.execute(
            "CREATE TABLE osakedata (osake TEXT,pvm TEXT,open REAL,high REAL,low REAL,close REAL,volume INTEGER,market TEXT)"
        )
        connection.executemany(
            "INSERT INTO osakedata VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (ticker, f"2024-01-0{day}", 100, 101, 99, 100 + day, 10, "usa")
                for day in (1, 2, 3, 4)
                for ticker in ("AAA", "BBB")
            ],
        )
    source_before = {path.name: path.read_bytes() for path in phase3.iterdir()}

    summaries = []
    for run in ("a", "b"):
        summaries.append(
            run_model_review(
                phase3_dir=phase3,
                taxonomy_csv=taxonomy,
                taxonomy_version="DC_TAXONOMY_V1",
                price_db=prices,
                market="usa",
                output_dir=Path("temp/datacenter_effective_weight_model_review") / run,
            )
        )

    assert summaries[0] == summaries[1]
    assert summaries[0]["production_mutation"] is False
    assert summaries[0]["weight_constants_changed"] is False
    assert {path.name: path.read_bytes() for path in phase3.iterdir()} == source_before


def test_model_review_rejects_output_outside_dedicated_temp_tree(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="output-dir"):
        run_model_review(
            phase3_dir=tmp_path / "missing-phase3",
            taxonomy_csv=tmp_path / "missing-taxonomy.csv",
            taxonomy_version="DC_TAXONOMY_V1",
            price_db=tmp_path / "missing-prices.db",
            market="usa",
            output_dir=Path("other"),
        )


def test_cli_forwards_model_review_arguments(monkeypatch, capsys):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {"status": "OK"}

    monkeypatch.setattr(cli, "run_model_review", fake_run)
    result = cli.main(
        [
            "--phase3-dir", "phase3",
            "--taxonomy-csv", "taxonomy.csv",
            "--taxonomy-version", "DC_TAXONOMY_V1",
            "--price-db", "prices.db",
            "--market", "usa",
            "--output-dir", "temp/datacenter_effective_weight_model_review/test",
        ]
    )

    assert result == 0
    assert captured["taxonomy_version"] == "DC_TAXONOMY_V1"
    assert "SUMMARY status=OK" in capsys.readouterr().out
