from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals.phase12d import PRODUCTION
from rawcandle.fundamentals.phase13b_foundation import online_backup
from rawcandle.fundamentals.phase13f_historical_delisted import (
    AREB_SECURITY_ID,
    CONTRACT_VERSION,
    OUTCOME_B,
    apply_historical_membership,
    areb_identity_and_listing_evidence,
    classify_areb_endpoints,
    create_copy_set,
    current_active_membership,
    current_ineligible_reason,
    downstream_areb_summary,
    ensure_historical_schema,
    historical_membership_on,
    membership_history,
    render_historical_report,
    run_copy_only_pilot,
)


def _canonical_copy(tmp_path: Path) -> Path:
    destination = tmp_path / "fundamentals_v4.db"
    online_backup(PRODUCTION["canonical"], destination)
    return destination


def _analysis_copy(tmp_path: Path) -> Path:
    destination = tmp_path / "fundamentals_analysis.db"
    online_backup(PRODUCTION["analysis"], destination)
    return destination


def test_areb_identity_listing_and_classification_evidence_is_stable() -> None:
    evidence = areb_identity_and_listing_evidence()

    assert evidence["identity_status"] == "RESOLVED"
    assert evidence["provider_listing_interval"]["permaticker"] == "637535"
    assert evidence["provider_listing_interval"]["cik"] == "0001648087"
    assert evidence["provider_listing_interval"]["start"] == "2022-02-07"
    assert evidence["provider_listing_interval"]["end"] == "2026-05-12"
    assert evidence["provider_listing_interval"]["isdelisted"] == "Y"
    assert evidence["local_classification"] == {
        "sector": "Consumer Cyclical",
        "industry": "Footwear & Accessories",
    }
    assert evidence["external_user_supplied_classification"] == {
        "sector": "Industrials",
        "industry": "Commercial Services & Supplies",
    }
    assert evidence["classification_status"] == "SOURCE_CLASSIFICATION_MISMATCH"
    assert evidence["fundamentals_classification_source"]["source_table"] == "data/osakedata.db.ticker_meta"
    assert evidence["fundamentals_classification_source"]["lookup"] == {"ticker": "AREB", "market": "usa"}
    assert evidence["fundamentals_classification_source"]["status"] == "CLASSIFICATION_READY"
    assert evidence["fundamentals_classification_source"]["historically_versioned"] is False
    assert evidence["datacenter_taxonomy_status"] == "NOT_MEMBER_BY_DESIGN"


def test_sndk_and_sndk1_identity_separation_remains_unchanged() -> None:
    with sqlite3.connect(f"file:{PRODUCTION['canonical'].resolve()}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute(
            "SELECT c.company_id,c.company_key,s.security_id,s.current_ticker,s.exchange,s.active "
            "FROM security s JOIN company c USING(company_id) "
            "WHERE UPPER(s.current_ticker) IN ('SNDK','SNDK1') ORDER BY s.current_ticker"
        )]

    assert [row["current_ticker"] for row in rows] == ["SNDK"]
    assert rows[0]["company_key"] != "SEC_PERMATICKER:643888:SNDK1"


def test_historical_schema_membership_and_dated_readers(tmp_path: Path) -> None:
    canonical = _canonical_copy(tmp_path)
    evidence = areb_identity_and_listing_evidence(canonical_db=canonical)

    schema = ensure_historical_schema(canonical, apply=True)
    membership = apply_historical_membership(canonical, evidence, apply=True)
    second = apply_historical_membership(canonical, evidence, apply=True)

    assert schema["outcome"] == "APPLIED"
    assert membership["identity"]["historical_universe_version_id"]
    assert second["outcome"] == "NO_CHANGE"
    assert current_active_membership(canonical)["active"] is False
    assert current_active_membership(canonical)["membership_status"] == "HISTORICAL_RETAINED_NO_ACTIVE_SECURITY"
    assert historical_membership_on(canonical, "2022-02-06")["historical_member"] is False
    assert historical_membership_on(canonical, "2022-02-07")["historical_member"] is True
    assert historical_membership_on(canonical, "2026-05-12")["historical_member"] is True
    assert historical_membership_on(canonical, "2026-05-13")["historical_member"] is False
    history = membership_history(canonical, AREB_SECURITY_ID)
    assert len(history) == 1
    assert history[0]["membership_status"] == "HISTORICAL_CLOSED_DELISTED"
    assert history[0]["current_active_membership"] == 0
    assert current_ineligible_reason(canonical)["current_ineligible_reason"] == "DELISTED_SECURITY"


def test_endpoint_classification_blocks_prelisting_and_post_delisting_investability(tmp_path: Path) -> None:
    canonical = _canonical_copy(tmp_path)
    evidence = areb_identity_and_listing_evidence(canonical_db=canonical)
    ensure_historical_schema(canonical, apply=True)
    apply_historical_membership(canonical, evidence, apply=True)

    endpoints = classify_areb_endpoints(canonical, PRODUCTION["market"], evidence)

    assert endpoints["counts"]["total_ttm_endpoints"] > 0
    assert endpoints["counts"]["prelisting_warmup_endpoints"] > 0
    assert endpoints["counts"]["listed_period_endpoints"] > 0
    assert endpoints["counts"]["post_delisting_endpoints"] >= 0
    if endpoints["counts"]["post_delisting_endpoints"] == 0:
        latest_available = max(
            row["ttm_source_available_date"] or row["source_availability_date"]
            for row in endpoints["rows"]
            if row["ttm_source_available_date"] or row["source_availability_date"]
        )
        assert latest_available <= endpoints["listing_end"]
    assert endpoints["counts"]["post_delisting_price_carry_forward_cases"] == 0
    assert all(
        not row["historically_investable"]
        for row in endpoints["rows"]
        if row["historical_endpoint_status"] != "LISTED_PERIOD_INVESTABLE"
    )


def test_downstream_summary_keeps_cross_sectional_layers_explicitly_blocked(tmp_path: Path) -> None:
    canonical = _canonical_copy(tmp_path)
    analysis = _analysis_copy(tmp_path)
    evidence = areb_identity_and_listing_evidence(canonical_db=canonical)
    ensure_historical_schema(canonical, apply=True)
    apply_historical_membership(canonical, evidence, apply=True)
    endpoints = classify_areb_endpoints(canonical, PRODUCTION["market"], evidence)

    summary = downstream_areb_summary(analysis, endpoints)

    assert summary["company_intrinsic_layers"]["score"]["listed_period_rows"] > 0
    assert summary["diagnostic_non_eight_endpoint_count"] > 0
    assert summary["diagnostic_evaluation_count_distribution"]["7"] > 0
    assert summary["diagnostic_evaluation_count_distribution"]["8"] > 0
    assert summary["historical_peer_status"] == "HISTORICAL_PEER_UNIVERSE_NOT_READY"
    assert "ACTIVE_UNIVERSE_FILTER" in summary["relative_valuation_status"]


def test_report_states_delisted_historical_security_without_current_percentiles(tmp_path: Path) -> None:
    canonical = _canonical_copy(tmp_path)
    analysis = _analysis_copy(tmp_path)
    evidence = areb_identity_and_listing_evidence(canonical_db=canonical)
    ensure_historical_schema(canonical, apply=True)
    apply_historical_membership(canonical, evidence, apply=True)
    endpoints = classify_areb_endpoints(canonical, PRODUCTION["market"], evidence)
    downstream = downstream_areb_summary(analysis, endpoints)

    report = render_historical_report(tmp_path, evidence, endpoints, downstream)
    text = Path(report["path"]).read_text(encoding="utf-8")

    assert "DELISTED — HISTORICAL SECURITY" in text
    assert "No current peer percentiles are shown." in text
    assert "not a current investable-company Snapshot" in text


def test_failure_injection_rolls_back_membership_transaction(tmp_path: Path) -> None:
    canonical = _canonical_copy(tmp_path)
    evidence = areb_identity_and_listing_evidence(canonical_db=canonical)
    ensure_historical_schema(canonical, apply=True)
    before = canonical.read_bytes()

    with pytest.raises(RuntimeError, match="INJECTED_PHASE13F_MEMBER_FAILURE"):
        apply_historical_membership(canonical, evidence, apply=True, inject_failure=True)

    assert canonical.read_bytes() == before


def test_protected_production_path_refusal() -> None:
    with pytest.raises(PermissionError):
        ensure_historical_schema(PRODUCTION["canonical"], apply=True)


def test_copy_only_pilot_smoke_without_heavy_rebuild(tmp_path: Path) -> None:
    result = run_copy_only_pilot(tmp_path / "phase13f_smoke", run_heavy=False)

    assert result["outcome"] == OUTCOME_B
    assert result["production_immutability"]["identical"] is True
    assert result["dated_readers"]["historical_inside_listing"]["historical_member"] is True
    assert result["second_apply_no_change"]["skipped"] is True
    assert (tmp_path / "phase13f_smoke" / "phase13f_result.json").exists()
