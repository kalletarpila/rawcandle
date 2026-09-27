from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from rawcandle.forecasts.contracts import (
    FAMILY_EARNINGS_HISTORY_REFERENCE,
    FAMILY_FISCAL_ESTIMATE,
    FAMILY_PRICE_TARGET,
    PROVIDER,
    STATE_NUMERIC_VALUE,
    STATE_NUMERIC_ZERO,
    STATE_TEXT_VALUE,
    STATUS_MALFORMED,
    STATUS_SUCCESS_CHANGED,
    STATUS_SUCCESS_UNCHANGED,
    STATUS_SUCCESS_WITH_DATA,
    STATUS_VALID_NO_DATA,
    CanonicalForecast,
    parse_payload,
)
from rawcandle.forecasts.schema import connect_forecasts_db
from rawcandle.forecasts.transport import YahooRawResult, utc_now


SUCCESS_AS_OF_STATUSES = (
    STATUS_SUCCESS_CHANGED,
    STATUS_SUCCESS_UNCHANGED,
    STATUS_VALID_NO_DATA,
)


@dataclass(frozen=True)
class PersistedFetch:
    fetch_id: str
    status: str
    snapshot_id: str | None
    content_hash: str | None


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _utc(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("forecast timestamps must include a UTC offset")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _identity_key(
    provider_symbol: str,
    company_id: int | None,
    security_id: int | None,
) -> str:
    if security_id is not None:
        return f"security:{int(security_id)}"
    if company_id is not None:
        return f"company:{int(company_id)}"
    return f"symbol:{provider_symbol.strip().upper()}"


def _state_parts(state: Mapping[str, Any]) -> tuple[str, str | None, str | None]:
    state_name = str(state["state"])
    value = state.get("value")
    if state_name in {STATE_NUMERIC_ZERO, STATE_NUMERIC_VALUE}:
        return state_name, str(value), None
    if state_name == STATE_TEXT_VALUE:
        return state_name, None, str(value)
    return state_name, None, None


def _text_value(state: Mapping[str, Any]) -> str | None:
    return str(state["value"]) if state.get("state") == STATE_TEXT_VALUE else None


class ForecastRepository:
    def __init__(
        self,
        db_path: str | Path,
        *,
        adapter: str = "yfinance",
        adapter_version: str,
        raw_retention_days: int = 30,
    ) -> None:
        self.db_path = Path(db_path)
        self.adapter = adapter
        self.adapter_version = adapter_version
        self.raw_retention_days = max(0, int(raw_retention_days))

    def start_run(
        self,
        *,
        scope: Mapping[str, Any] | None = None,
        started_at_utc: str | None = None,
        run_id: str | None = None,
    ) -> str:
        resolved_run_id = run_id or uuid.uuid4().hex
        with connect_forecasts_db(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO forecast_run(
                    run_id,provider,adapter,adapter_version,started_at_utc,status,
                    scope_json,counters_json
                ) VALUES(?,?,?,?,?,'RUNNING',?,'{}')
                """,
                (
                    resolved_run_id,
                    PROVIDER,
                    self.adapter,
                    self.adapter_version,
                    _utc(started_at_utc or utc_now()),
                    _json(scope or {}),
                ),
            )
        return resolved_run_id

    def complete_run(
        self,
        run_id: str,
        *,
        completed_at_utc: str | None = None,
    ) -> dict[str, int]:
        with connect_forecasts_db(self.db_path) as connection:
            rows = connection.execute(
                "SELECT status,COUNT(*) count FROM forecast_fetch WHERE run_id=? GROUP BY status",
                (run_id,),
            ).fetchall()
            counters = {str(row["status"]): int(row["count"]) for row in rows}
            failures = sum(
                count
                for status, count in counters.items()
                if status not in SUCCESS_AS_OF_STATUSES
            )
            successes = sum(
                count for status, count in counters.items() if status in SUCCESS_AS_OF_STATUSES
            )
            status = "SUCCESS" if failures == 0 else ("PARTIAL" if successes else "FAILED")
            connection.execute(
                """
                UPDATE forecast_run
                SET completed_at_utc=?,status=?,counters_json=?
                WHERE run_id=?
                """,
                (_utc(completed_at_utc or utc_now()), status, _json(counters), run_id),
            )
            if connection.total_changes == 0:
                raise LookupError(f"forecast run not found: {run_id}")
        return counters

    def _retain_until(self, fetched_at_utc: str) -> str:
        parsed = datetime.fromisoformat(fetched_at_utc.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return (parsed + timedelta(days=self.raw_retention_days)).astimezone(
            timezone.utc
        ).isoformat().replace("+00:00", "Z")

    def _store_raw_evidence(self, connection: Any, result: YahooRawResult) -> str | None:
        if (
            self.raw_retention_days <= 0
            or result.raw_hash is None
            or (result.raw_body is None and result.raw_payload is None)
        ):
            return None
        connection.execute(
            """
            INSERT OR IGNORE INTO forecast_raw_evidence(
                raw_hash,provider,forecast_family,body_text,first_seen_at_utc,
                retain_until_utc
            ) VALUES(?,?,?,?,?,?)
            """,
            (
                result.raw_hash,
                PROVIDER,
                result.forecast_family,
                result.raw_body if result.raw_body is not None else _json(result.raw_payload),
                _utc(result.fetched_at_utc),
                self._retain_until(result.fetched_at_utc),
            ),
        )
        return result.raw_hash

    def _latest_snapshot(
        self, connection: Any, family: str, identity_key: str, fetched_at_utc: str
    ) -> Any:
        return connection.execute(
            """
            SELECT s.snapshot_id,s.content_hash
            FROM forecast_fetch f
            JOIN forecast_snapshot s ON s.snapshot_id=f.snapshot_id
            WHERE f.provider=? AND f.forecast_family=? AND f.identity_key=?
              AND f.status IN ('SUCCESS_CHANGED','SUCCESS_UNCHANGED')
              AND f.fetched_at_utc<=?
            ORDER BY f.fetched_at_utc DESC,f.rowid DESC
            LIMIT 1
            """,
            (PROVIDER, family, identity_key, fetched_at_utc),
        ).fetchone()

    def record_fetch(
        self,
        run_id: str,
        result: YahooRawResult,
        *,
        company_id: int | None = None,
        security_id: int | None = None,
    ) -> PersistedFetch:
        fetch_id = uuid.uuid4().hex
        identity_key = _identity_key(result.provider_symbol, company_id, security_id)
        requested_at_utc = _utc(result.requested_at_utc)
        fetched_at_utc = _utc(result.fetched_at_utc)
        parsed = None
        final_status = result.status
        if result.status in {STATUS_SUCCESS_WITH_DATA, STATUS_VALID_NO_DATA}:
            parsed = parse_payload(result.forecast_family, result.raw_payload)
            final_status = parsed.status

        with connect_forecasts_db(self.db_path) as connection:
            evidence_hash = self._store_raw_evidence(connection, result)
            snapshot_id: str | None = None
            content_hash: str | None = None
            diagnostics: dict[str, Any] = {}

            if parsed is not None and parsed.forecast is not None:
                diagnostics["schema_drift"] = list(parsed.forecast.schema_drift)
            if result.error_message:
                diagnostics["error_message"] = result.error_message
            if parsed is not None and parsed.error_message:
                diagnostics["parser_error_message"] = parsed.error_message

            if final_status == STATUS_SUCCESS_WITH_DATA:
                assert parsed is not None and parsed.forecast is not None
                forecast = parsed.forecast
                content_hash = forecast.content_hash
                latest = self._latest_snapshot(
                    connection, result.forecast_family, identity_key, fetched_at_utc
                )
                if latest is not None and latest["content_hash"] == content_hash:
                    final_status = STATUS_SUCCESS_UNCHANGED
                    snapshot_id = str(latest["snapshot_id"])
                else:
                    final_status = STATUS_SUCCESS_CHANGED
                    existing = connection.execute(
                        """
                        SELECT snapshot_id FROM forecast_snapshot
                        WHERE provider=? AND forecast_family=? AND identity_key=?
                          AND content_hash=?
                        """,
                        (PROVIDER, result.forecast_family, identity_key, content_hash),
                    ).fetchone()
                    if existing is not None:
                        snapshot_id = str(existing["snapshot_id"])
                    else:
                        snapshot_id = uuid.uuid4().hex
                        connection.execute(
                            """
                            INSERT INTO forecast_snapshot(
                                snapshot_id,provider,forecast_family,identity_key,
                                company_id,security_id,provider_symbol,first_fetch_id,
                                first_seen_at_utc,content_hash,contract_version,
                                canonical_payload_json,raw_evidence_hash,schema_drift_json
                            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                            """,
                            (
                                snapshot_id, PROVIDER, result.forecast_family, identity_key,
                                company_id, security_id, result.provider_symbol, fetch_id,
                                fetched_at_utc, content_hash, forecast.contract_version,
                                forecast.canonical_json, evidence_hash,
                                _json(list(forecast.schema_drift)),
                            ),
                        )
                        self._insert_normalized(connection, snapshot_id, forecast)

            error_code = result.error_code
            error_class = result.error_class
            if final_status == STATUS_MALFORMED and parsed is not None:
                error_code = parsed.error_code or error_code
                error_class = STATUS_MALFORMED

            connection.execute(
                """
                INSERT INTO forecast_fetch(
                    fetch_id,run_id,provider,adapter,adapter_version,company_id,
                    security_id,identity_key,provider_symbol,forecast_family,
                    requested_at_utc,fetched_at_utc,status,http_status,attempt_count,
                    error_class,error_code,content_hash,snapshot_id,raw_evidence_hash,
                    diagnostic_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    fetch_id, run_id, PROVIDER, self.adapter, self.adapter_version,
                    company_id, security_id, identity_key, result.provider_symbol,
                    result.forecast_family, requested_at_utc,
                    fetched_at_utc, final_status, result.http_status,
                    result.attempt_count, error_class, error_code, content_hash,
                    snapshot_id, evidence_hash, _json(diagnostics),
                ),
            )
        return PersistedFetch(fetch_id, final_status, snapshot_id, content_hash)

    def _insert_normalized(
        self,
        connection: Any,
        snapshot_id: str,
        forecast: CanonicalForecast,
    ) -> None:
        if forecast.family == FAMILY_FISCAL_ESTIMATE:
            self._insert_estimates(connection, snapshot_id, forecast.payload)
        elif forecast.family == FAMILY_PRICE_TARGET:
            self._insert_price_targets(connection, snapshot_id, forecast.payload)
        elif forecast.family == FAMILY_EARNINGS_HISTORY_REFERENCE:
            self._insert_earnings_history(connection, snapshot_id, forecast.payload)
        else:
            raise ValueError(f"unsupported normalized family: {forecast.family}")

    def _insert_estimate_row(
        self,
        connection: Any,
        snapshot_id: str,
        row: Mapping[str, Any],
        methodology: Mapping[str, Any],
        metric: str,
        statistic: str,
        state: Mapping[str, Any],
        *,
        currency: str | None,
        unit: str,
        source_path: str,
        analyst_count: str | None = None,
    ) -> None:
        value_state, numeric, text = _state_parts(state)
        methodology_state, _, methodology_text = _state_parts(methodology)
        connection.execute(
            """
            INSERT INTO forecast_estimate(
                snapshot_id,occurrence_index,provider_horizon,provider_end_date,
                provider_methodology,provider_methodology_state,metric,statistic,
                value_numeric,value_text,value_state,currency,unit,source_path,
                analyst_count,link_status
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'UNLINKED')
            """,
            (
                snapshot_id, row["occurrenceIndex"], row["providerHorizon"],
                row["providerEndDate"], methodology_text, methodology_state,
                metric, statistic, numeric, text, value_state, currency, unit,
                source_path, analyst_count,
            ),
        )

    def _insert_estimates(
        self, connection: Any, snapshot_id: str, payload: Mapping[str, Any]
    ) -> None:
        methodology = payload["defaultMethodology"]
        for row in payload["rows"]:
            earnings = row["earningsEstimate"]
            revenue = row["revenueEstimate"]
            eps_trend = row["epsTrend"]
            revisions = row["epsRevisions"]
            eps_currency = _text_value(earnings["earningsCurrency"])
            revenue_currency = _text_value(revenue["revenueCurrency"])
            trend_currency = _text_value(eps_trend["epsTrendCurrency"])
            revision_currency = _text_value(revisions["epsRevisionsCurrency"])
            _, eps_count, _ = _state_parts(earnings["numberOfAnalysts"])
            _, revenue_count, _ = _state_parts(revenue["numberOfAnalysts"])

            self._insert_estimate_row(
                connection, snapshot_id, row, methodology, "YAHOO_ROW_GROWTH",
                "VALUE", row["topLevelGrowth"], currency=None, unit="RATIO",
                source_path="earningsTrend.trend[].growth",
            )
            for source, statistic in (
                ("avg", "AVG"), ("low", "LOW"), ("high", "HIGH"),
                ("yearAgoEps", "YEAR_AGO"),
            ):
                self._insert_estimate_row(
                    connection, snapshot_id, row, methodology, "EPS_ESTIMATE",
                    statistic, earnings[source], currency=eps_currency,
                    unit="CURRENCY_PER_SHARE",
                    source_path=f"earningsTrend.trend[].earningsEstimate.{source}",
                    analyst_count=eps_count,
                )
            self._insert_estimate_row(
                connection, snapshot_id, row, methodology, "EPS_ANALYST_COUNT",
                "VALUE", earnings["numberOfAnalysts"], currency=None, unit="COUNT",
                source_path="earningsTrend.trend[].earningsEstimate.numberOfAnalysts",
            )
            self._insert_estimate_row(
                connection, snapshot_id, row, methodology,
                "EARNINGS_ESTIMATE_GROWTH", "VALUE", earnings["growth"],
                currency=None, unit="RATIO",
                source_path="earningsTrend.trend[].earningsEstimate.growth",
                analyst_count=eps_count,
            )
            for source, statistic in (
                ("avg", "AVG"), ("low", "LOW"), ("high", "HIGH"),
                ("yearAgoRevenue", "YEAR_AGO"),
            ):
                self._insert_estimate_row(
                    connection, snapshot_id, row, methodology, "REVENUE_ESTIMATE",
                    statistic, revenue[source], currency=revenue_currency,
                    unit="CURRENCY",
                    source_path=f"earningsTrend.trend[].revenueEstimate.{source}",
                    analyst_count=revenue_count,
                )
            self._insert_estimate_row(
                connection, snapshot_id, row, methodology, "REVENUE_ANALYST_COUNT",
                "VALUE", revenue["numberOfAnalysts"], currency=None, unit="COUNT",
                source_path="earningsTrend.trend[].revenueEstimate.numberOfAnalysts",
            )
            self._insert_estimate_row(
                connection, snapshot_id, row, methodology,
                "REVENUE_ESTIMATE_GROWTH", "VALUE", revenue["growth"],
                currency=None, unit="RATIO",
                source_path="earningsTrend.trend[].revenueEstimate.growth",
                analyst_count=revenue_count,
            )
            for source, statistic in (
                ("current", "CURRENT"), ("7daysAgo", "7D_AGO"),
                ("30daysAgo", "30D_AGO"), ("60daysAgo", "60D_AGO"),
                ("90daysAgo", "90D_AGO"),
            ):
                self._insert_estimate_row(
                    connection, snapshot_id, row, methodology, "EPS_TREND",
                    statistic, eps_trend[source], currency=trend_currency,
                    unit="CURRENCY_PER_SHARE",
                    source_path=f"earningsTrend.trend[].epsTrend.{source}",
                )
            for source, statistic in (
                ("upLast7days", "UP_7D"), ("upLast30days", "UP_30D"),
                ("downLast7Days", "DOWN_7D"),
                ("downLast30days", "DOWN_30D"),
                ("downLast90days", "DOWN_90D"),
            ):
                self._insert_estimate_row(
                    connection, snapshot_id, row, methodology, "EPS_REVISION_COUNT",
                    statistic, revisions[source], currency=revision_currency,
                    unit="COUNT",
                    source_path=f"earningsTrend.trend[].epsRevisions.{source}",
                )

    def _insert_price_targets(
        self, connection: Any, snapshot_id: str, payload: Mapping[str, Any]
    ) -> None:
        currency = _text_value(payload["currency"])
        source_names = {
            "current": "currentPrice", "low": "targetLowPrice",
            "high": "targetHighPrice", "mean": "targetMeanPrice",
            "median": "targetMedianPrice",
        }
        for statistic, state in payload["values"].items():
            value_state, numeric, _ = _state_parts(state)
            connection.execute(
                """
                INSERT INTO forecast_price_target(
                    snapshot_id,statistic,value_numeric,value_state,currency,source_path
                ) VALUES(?,?,?,?,?,?)
                """,
                (
                    snapshot_id, statistic, numeric, value_state, currency,
                    f"financialData.{source_names[statistic]}",
                ),
            )

    def _insert_earnings_history(
        self, connection: Any, snapshot_id: str, payload: Mapping[str, Any]
    ) -> None:
        methodology_state, _, methodology = _state_parts(payload["defaultMethodology"])
        for row in payload["rows"]:
            values = {
                key: _state_parts(row[key])
                for key in ("epsEstimate", "epsActual", "epsDifference", "surprisePercent")
            }
            connection.execute(
                """
                INSERT INTO forecast_earnings_history_reference(
                    snapshot_id,occurrence_index,provider_period,provider_quarter_date,
                    provider_methodology,provider_methodology_state,currency,
                    eps_estimate,eps_estimate_state,eps_actual,eps_actual_state,
                    eps_difference,eps_difference_state,surprise_percent,
                    surprise_percent_state,authority
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'YAHOO_PROVIDER_REFERENCE')
                """,
                (
                    snapshot_id, row["occurrenceIndex"], row["providerPeriod"],
                    row["providerQuarterDate"], methodology, methodology_state,
                    _text_value(row["currency"]), values["epsEstimate"][1],
                    values["epsEstimate"][0], values["epsActual"][1],
                    values["epsActual"][0], values["epsDifference"][1],
                    values["epsDifference"][0], values["surprisePercent"][1],
                    values["surprisePercent"][0],
                ),
            )

    def as_known_at(
        self,
        *,
        forecast_family: str,
        timestamp_utc: str,
        provider_symbol: str,
        company_id: int | None = None,
        security_id: int | None = None,
    ) -> dict[str, Any] | None:
        identity_key = _identity_key(provider_symbol, company_id, security_id)
        placeholders = ",".join("?" for _ in SUCCESS_AS_OF_STATUSES)
        with connect_forecasts_db(self.db_path) as connection:
            fetch = connection.execute(
                f"""
                SELECT * FROM forecast_fetch
                WHERE provider=? AND forecast_family=? AND identity_key=?
                  AND fetched_at_utc<=? AND status IN ({placeholders})
                ORDER BY fetched_at_utc DESC,rowid DESC
                LIMIT 1
                """,
                (
                    PROVIDER, forecast_family, identity_key, _utc(timestamp_utc),
                    *SUCCESS_AS_OF_STATUSES,
                ),
            ).fetchone()
            if fetch is None:
                return None
            result: dict[str, Any] = {"fetch": dict(fetch), "snapshot": None, "records": []}
            if fetch["snapshot_id"] is None:
                return result
            snapshot = connection.execute(
                "SELECT * FROM forecast_snapshot WHERE snapshot_id=?",
                (fetch["snapshot_id"],),
            ).fetchone()
            result["snapshot"] = dict(snapshot)
            table = {
                FAMILY_FISCAL_ESTIMATE: "forecast_estimate",
                FAMILY_PRICE_TARGET: "forecast_price_target",
                FAMILY_EARNINGS_HISTORY_REFERENCE: "forecast_earnings_history_reference",
            }[forecast_family]
            result["records"] = [
                dict(row)
                for row in connection.execute(
                    f"SELECT * FROM {table} WHERE snapshot_id=? ORDER BY 1",
                    (fetch["snapshot_id"],),
                )
            ]
            return result
