from __future__ import annotations


def build_watchlist_membership_summary(
    *,
    source_watchlist_tickers: list[str],
    loaded_watchlist_tickers: list[str],
) -> dict[str, object]:
    missing_from_loaded = sorted(set(source_watchlist_tickers) - set(loaded_watchlist_tickers))
    loaded_only = sorted(set(loaded_watchlist_tickers) - set(source_watchlist_tickers))
    drift_detected = bool(missing_from_loaded or loaded_only)
    return {
        "watchlist_membership_status": "DRIFT_DETECTED" if drift_detected else "MATCH",
        "watchlist_sync_required": drift_detected,
        "watchlist_source_member_count": len(source_watchlist_tickers),
        "watchlist_loaded_member_count": len(loaded_watchlist_tickers),
        "watchlist_missing_in_loaded_count": len(missing_from_loaded),
        "watchlist_loaded_only_count": len(loaded_only),
        "watchlist_missing_in_loaded": missing_from_loaded,
        "watchlist_loaded_only": loaded_only,
        "loaded_watchlist_tickers": loaded_watchlist_tickers,
        "source_watchlist_tickers": source_watchlist_tickers,
    }


def extract_watchlist_membership_fields(summary: dict[str, object]) -> dict[str, object]:
    planner_summary = summary.get("planner_summary")
    source = planner_summary if isinstance(planner_summary, dict) else summary
    compatibility_summary = source.get("compatibility_summary")
    if not isinstance(compatibility_summary, dict):
        return {
            "watchlist_membership_status": "UNKNOWN",
            "watchlist_sync_required": False,
            "watchlist_source_member_count": 0,
            "watchlist_loaded_member_count": 0,
            "watchlist_missing_in_loaded_count": 0,
            "watchlist_loaded_only_count": 0,
            "watchlist_missing_in_loaded": [],
            "watchlist_loaded_only": [],
        }
    return {
        "watchlist_membership_status": str(compatibility_summary.get("watchlist_membership_status") or "UNKNOWN"),
        "watchlist_sync_required": bool(compatibility_summary.get("watchlist_sync_required") or False),
        "watchlist_source_member_count": int(compatibility_summary.get("watchlist_source_member_count") or 0),
        "watchlist_loaded_member_count": int(compatibility_summary.get("watchlist_loaded_member_count") or 0),
        "watchlist_missing_in_loaded_count": int(compatibility_summary.get("watchlist_missing_in_loaded_count") or 0),
        "watchlist_loaded_only_count": int(compatibility_summary.get("watchlist_loaded_only_count") or 0),
        "watchlist_missing_in_loaded": list(compatibility_summary.get("watchlist_missing_in_loaded") or []),
        "watchlist_loaded_only": list(compatibility_summary.get("watchlist_loaded_only") or []),
    }
