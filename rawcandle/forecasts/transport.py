from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from yfinance.data import YfData
from yfinance.exceptions import YFRateLimitError
from yfinance.scrapers.quote import _QUOTE_SUMMARY_URL_

from rawcandle.forecasts.contracts import (
    FAMILY_EARNINGS_HISTORY_REFERENCE,
    FAMILY_FISCAL_ESTIMATE,
    FAMILY_PRICE_TARGET,
    STATUS_MALFORMED,
    STATUS_PROVIDER_SYMBOL_UNAVAILABLE,
    STATUS_RATE_LIMITED,
    STATUS_TRANSIENT_FAILURE,
    parse_payload,
)


FAMILY_MODULE = {
    FAMILY_FISCAL_ESTIMATE: "earningsTrend",
    FAMILY_PRICE_TARGET: "financialData",
    FAMILY_EARNINGS_HISTORY_REFERENCE: "earningsHistory",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class YahooTransportConfig:
    timeout_seconds: float = 30.0
    max_retries: int = 2
    retry_backoff_seconds: float = 1.0
    minimum_interval_seconds: float = 0.5
    max_concurrency: int = 1
    raw_retention_days: int = 30

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if self.retry_backoff_seconds < 0 or self.minimum_interval_seconds < 0:
            raise ValueError("transport delays cannot be negative")
        if self.max_concurrency < 1:
            raise ValueError("max_concurrency must be at least one")
        if self.raw_retention_days < 0:
            raise ValueError("raw_retention_days cannot be negative")


@dataclass(frozen=True)
class YahooRawResult:
    requested_at_utc: str
    fetched_at_utc: str
    provider_symbol: str
    forecast_family: str
    http_status: int | None
    status: str
    success: bool
    error_class: str | None
    error_code: str | None
    error_message: str | None
    raw_payload: Mapping[str, Any] | None
    raw_body: str | None
    raw_hash: str | None
    attempt_count: int


class YahooRequestLimiter:
    def __init__(
        self,
        minimum_interval_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.minimum_interval_seconds = max(0.0, minimum_interval_seconds)
        self._clock = clock
        self._sleeper = sleeper
        self._last_request_at: float | None = None
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            if self._last_request_at is not None:
                remaining = self.minimum_interval_seconds - (now - self._last_request_at)
                if remaining > 0:
                    self._sleeper(remaining)
                    now = self._clock()
            self._last_request_at = now


_PROCESS_LIMITER = YahooRequestLimiter(0.5)


Requester = Callable[[str, Mapping[str, Any], float], Any]


class YahooForecastTransport:
    def __init__(
        self,
        *,
        config: YahooTransportConfig | None = None,
        requester: Requester | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        limiter: YahooRequestLimiter | None = None,
        now: Callable[[], str] = utc_now,
    ) -> None:
        self.config = config or YahooTransportConfig()
        self._data = YfData() if requester is None else None
        self._requester = requester or self._request
        self._sleeper = sleeper
        self._limiter = limiter or (
            _PROCESS_LIMITER
            if self.config.minimum_interval_seconds == 0.5
            else YahooRequestLimiter(self.config.minimum_interval_seconds)
        )
        self._semaphore = threading.BoundedSemaphore(self.config.max_concurrency)
        self._now = now

    def _request(self, url: str, params: Mapping[str, Any], timeout: float) -> Any:
        assert self._data is not None
        return self._data.get(url, params=dict(params), timeout=timeout)

    def _backoff(self, attempt_count: int) -> None:
        delay = self.config.retry_backoff_seconds * (2 ** (attempt_count - 1))
        if delay > 0:
            self._sleeper(delay)

    def _limited_request(
        self,
        url: str,
        params: Mapping[str, Any],
    ) -> Any:
        with self._semaphore:
            self._limiter.wait()
            return self._requester(url, params, self.config.timeout_seconds)

    def _terminal(
        self,
        *,
        requested_at: str,
        symbol: str,
        family: str,
        status: str,
        attempts: int,
        http_status: int | None = None,
        payload: Mapping[str, Any] | None = None,
        raw_body: str | None = None,
        raw_hash: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> YahooRawResult:
        success = status in {"SUCCESS_WITH_DATA", "VALID_NO_DATA"}
        return YahooRawResult(
            requested_at_utc=requested_at,
            fetched_at_utc=self._now(),
            provider_symbol=symbol,
            forecast_family=family,
            http_status=http_status,
            status=status,
            success=success,
            error_class=None if success else status,
            error_code=error_code,
            error_message=error_message,
            raw_payload=payload,
            raw_body=raw_body,
            raw_hash=raw_hash,
            attempt_count=attempts,
        )

    def fetch(self, provider_symbol: str, forecast_family: str) -> YahooRawResult:
        symbol = provider_symbol.strip().upper()
        if not symbol:
            raise ValueError("provider_symbol is required")
        try:
            module = FAMILY_MODULE[forecast_family]
        except KeyError as exc:
            raise ValueError(f"unsupported forecast family: {forecast_family}") from exc

        requested_at = self._now()
        url = f"{_QUOTE_SUMMARY_URL_}/{symbol}"
        params = {
            "modules": module,
            "corsDomain": "finance.yahoo.com",
            "formatted": "false",
            "symbol": symbol,
        }
        max_attempts = self.config.max_retries + 1

        for attempt in range(1, max_attempts + 1):
            try:
                response = self._limited_request(url, params)
            except YFRateLimitError as exc:
                if attempt < max_attempts:
                    self._backoff(attempt)
                    continue
                return self._terminal(
                    requested_at=requested_at,
                    symbol=symbol,
                    family=forecast_family,
                    status=STATUS_RATE_LIMITED,
                    attempts=attempt,
                    http_status=429,
                    error_code=type(exc).__name__,
                    error_message=str(exc),
                )
            except Exception as exc:
                if attempt < max_attempts:
                    self._backoff(attempt)
                    continue
                return self._terminal(
                    requested_at=requested_at,
                    symbol=symbol,
                    family=forecast_family,
                    status=STATUS_TRANSIENT_FAILURE,
                    attempts=attempt,
                    error_code=type(exc).__name__,
                    error_message=str(exc),
                )

            http_status = int(response.status_code)
            raw_text = str(getattr(response, "text", ""))
            raw_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
            try:
                payload = response.json()
            except (ValueError, json.JSONDecodeError) as exc:
                if 500 <= http_status <= 599 and attempt < max_attempts:
                    self._backoff(attempt)
                    continue
                status = (
                    STATUS_TRANSIENT_FAILURE
                    if 500 <= http_status <= 599
                    else STATUS_MALFORMED
                )
                return self._terminal(
                    requested_at=requested_at,
                    symbol=symbol,
                    family=forecast_family,
                    status=status,
                    attempts=attempt,
                    http_status=http_status,
                    raw_body=raw_text,
                    raw_hash=raw_hash,
                    error_code=type(exc).__name__,
                    error_message="response body is not valid JSON",
                )

            payload_mapping = payload if isinstance(payload, Mapping) else None
            if http_status == 429:
                if attempt < max_attempts:
                    self._backoff(attempt)
                    continue
                return self._terminal(
                    requested_at=requested_at,
                    symbol=symbol,
                    family=forecast_family,
                    status=STATUS_RATE_LIMITED,
                    attempts=attempt,
                    http_status=http_status,
                    payload=payload_mapping,
                    raw_body=raw_text,
                    raw_hash=raw_hash,
                    error_code="HTTP_429",
                )
            if 500 <= http_status <= 599:
                if attempt < max_attempts:
                    self._backoff(attempt)
                    continue
                return self._terminal(
                    requested_at=requested_at,
                    symbol=symbol,
                    family=forecast_family,
                    status=STATUS_TRANSIENT_FAILURE,
                    attempts=attempt,
                    http_status=http_status,
                    payload=payload_mapping,
                    raw_body=raw_text,
                    raw_hash=raw_hash,
                    error_code=f"HTTP_{http_status}",
                )

            parsed = parse_payload(forecast_family, payload)
            status = parsed.status
            if http_status == 404 and status != STATUS_PROVIDER_SYMBOL_UNAVAILABLE:
                status = STATUS_MALFORMED
            return self._terminal(
                requested_at=requested_at,
                symbol=symbol,
                family=forecast_family,
                status=status,
                attempts=attempt,
                http_status=http_status,
                payload=payload_mapping,
                raw_body=raw_text,
                raw_hash=raw_hash,
                error_code=parsed.error_code,
                error_message=parsed.error_message,
            )

        raise AssertionError("unreachable transport attempt state")
