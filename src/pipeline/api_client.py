"""
Polluxa API Client — Secure, rate-limited API client with retry logic.
Part 2: API Engineering & Data Pipeline.

Handles:
- Token-based authentication
- Exponential backoff with jitter on transient failures
- Rate-limit awareness (respects HTTP 429 / Retry-After headers)
- Structured logging of every request
"""

import time
import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
import structlog

from config.settings import (
    POLLUXA_API_BASE_URL,
    POLLUXA_API_KEY,
    POLLUXA_API_SECRET,
    PIPELINE_MAX_RETRIES,
    PIPELINE_RETRY_BACKOFF_BASE,
    PIPELINE_RATE_LIMIT_RPM,
)

logger = structlog.get_logger()


class RateLimitError(Exception):
    """Raised when the API returns HTTP 429 (Too Many Requests)."""
    pass


class APIClientError(Exception):
    """Raised for non-retryable API errors (4xx except 429)."""
    pass


class APIServerError(Exception):
    """Raised for retryable server errors (5xx)."""
    pass


class PolluxaAPIClient:
    """
    Production-ready API client for the Polluxa platform.

    Features:
    - Token management with secure header injection
    - Automatic retry with exponential backoff on 5xx and 429
    - Rate-limit throttle (respects RPM ceiling)
    - Structured JSON logging of all requests/responses
    """

    def __init__(self, base_url: str | None = None, api_key: str | None = None, api_secret: str | None = None):
        self.base_url = (base_url or POLLUXA_API_BASE_URL).rstrip("/")
        self.api_key = api_key or POLLUXA_API_KEY
        self.api_secret = api_secret or POLLUXA_API_SECRET
        self.session = requests.Session()
        self._min_request_interval = 60.0 / PIPELINE_RATE_LIMIT_RPM
        self._last_request_time = 0.0

        # Set auth headers (token-based)
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "X-API-Secret": self.api_secret,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "LinkedInAnalyticsPlatform/1.0",
        })

    def _throttle(self) -> None:
        """Enforce rate-limit by sleeping if requests come too fast."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            sleep_time = self._min_request_interval - elapsed
            logger.debug("rate_limit_throttle", sleep_seconds=round(sleep_time, 2))
            time.sleep(sleep_time)

    @retry(
        stop=stop_after_attempt(PIPELINE_MAX_RETRIES + 1),
        wait=wait_exponential(multiplier=1, min=PIPELINE_RETRY_BACKOFF_BASE, max=60),
        retry=retry_if_exception_type((RateLimitError, APIServerError, requests.ConnectionError, requests.Timeout)),
    )
    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """
        Core request method with retry, rate-limit, and error classification.

        Args:
            method: HTTP method ('GET', 'POST', etc.)
            endpoint: API endpoint path (e.g., '/agents/activities')
            **kwargs: Passed to requests.Session.request()

        Returns:
            Parsed JSON response as dict.

        Raises:
            RateLimitError: On HTTP 429 (retryable).
            APIServerError: On HTTP 5xx (retryable).
            APIClientError: On HTTP 4xx except 429 (not retryable).
        """
        self._throttle()

        url = f"{self.base_url}{endpoint}"
        log = logger.bind(method=method, url=url)

        log.info("api_request_start")
        self._last_request_time = time.time()

        try:
            response = self.session.request(method, url, timeout=30, **kwargs)
        except requests.Timeout:
            log.warning("api_request_timeout")
            raise
        except requests.ConnectionError:
            log.warning("api_connection_error")
            raise

        log = log.bind(status_code=response.status_code)

        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 5))
            log.warning("rate_limited", retry_after=retry_after)
            time.sleep(retry_after)
            raise RateLimitError(f"Rate limited. Retry after {retry_after}s")

        if 500 <= response.status_code < 600:
            log.error("api_server_error", body=response.text[:500])
            raise APIServerError(f"Server error {response.status_code}")

        if 400 <= response.status_code < 500:
            log.error("api_client_error", body=response.text[:500])
            raise APIClientError(f"Client error {response.status_code}: {response.text[:200]}")

        log.info("api_request_success")
        return response.json() if response.text else {}

    # ----------------------------------------------------------------
    # Public API methods — map to Polluxa endpoints
    # ----------------------------------------------------------------

    def get_agents(self) -> list[dict]:
        """Fetch all LinkedIn agent accounts."""
        return self._request("GET", "/agents")

    def get_activities(self, since: str | None = None, limit: int = 100, offset: int = 0) -> list[dict]:
        """
        Fetch outreach activities with optional watermark-based filtering.

        Args:
            since: ISO datetime string — only return activities after this timestamp.
            limit: Max records per page.
            offset: Pagination offset.

        Returns:
            List of activity records.
        """
        params = {"limit": limit, "offset": offset}
        if since:
            params["since"] = since
        return self._request("GET", "/agents/activities", params=params)

    def get_leads(self, campaign_id: str | None = None, since: str | None = None) -> list[dict]:
        """Fetch leads, optionally filtered by campaign and/or watermark."""
        params = {}
        if campaign_id:
            params["campaign_id"] = campaign_id
        if since:
            params["since"] = since
        return self._request("GET", "/leads", params=params)

    def get_campaigns(self) -> list[dict]:
        """Fetch all campaigns."""
        return self._request("GET", "/campaigns")

    def get_message_templates(self) -> list[dict]:
        """Fetch all message templates."""
        return self._request("GET", "/message-templates")

    def get_daily_stats(self, agent_id: str, date: str) -> dict:
        """Fetch daily aggregated stats for a specific agent on a specific date."""
        return self._request("GET", f"/agents/{agent_id}/stats/{date}")
