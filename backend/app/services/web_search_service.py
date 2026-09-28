"""
web_search_service.py
---------------------
SearXNG-only web search abstraction for the Installation Research Agent.

This service is the SOLE search backend for installation research.
It does NOT call Tavily, Google, Bing, or any other external provider.
All search traffic goes exclusively to the locally hosted SearXNG instance.

Configuration required in .env:
    SEARXNG_BASE_URL=http://localhost:8080

SearXNG must have JSON output enabled (Settings → Formats → JSON checked).
"""

import time
from typing import List, Optional, TypedDict

import httpx
from app.core.config import settings
from app.core.logger import logger


class SearchResult(TypedDict):
    title: str
    url: str
    content: str
    engine: Optional[str]
    score: Optional[float]


class SearXNGUnavailableError(Exception):
    """Raised when SearXNG cannot be reached or returns an unexpected response."""


class SearXNGJSONDisabledError(Exception):
    """Raised when SearXNG is reachable but JSON format is not enabled."""


class WebSearchService:
    """
    Thin wrapper around the SearXNG JSON search API.

    Usage:
        results = WebSearchService.search("Appium 3.1.0 Ubuntu install", max_results=5)
    """

    # Connection + read timeouts (seconds)
    _CONNECT_TIMEOUT: float = 5.0
    _READ_TIMEOUT: float = 15.0

    @classmethod
    def _base_url(cls) -> str:
        url = settings.SEARXNG_BASE_URL.rstrip("/")
        if not url:
            raise SearXNGUnavailableError(
                "SEARXNG_BASE_URL is not configured. "
                "Set it in .env: SEARXNG_BASE_URL=http://localhost:8080"
            )
        if not (url.startswith("http://") or url.startswith("https://")):
            raise SearXNGUnavailableError(
                f"SEARXNG_BASE_URL '{url}' must start with http:// or https://"
            )
        return url

    @classmethod
    def health_check(cls) -> bool:
        """
        Lightweight health check: sends a test query and verifies JSON is enabled.
        Returns True if SearXNG is reachable and returning JSON results.
        Does NOT raise — returns False with a warning log on any failure.
        """
        try:
            base = cls._base_url()
        except SearXNGUnavailableError as e:
            logger.warning(f"[WebSearchService] Health check skipped: {e}")
            return False

        try:
            with httpx.Client(
                timeout=httpx.Timeout(cls._CONNECT_TIMEOUT, read=cls._READ_TIMEOUT)
            ) as client:
                resp = client.get(
                    f"{base}/search",
                    params={"q": "test", "format": "json"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if "results" in data:
                        logger.info("[WebSearchService] SearXNG health check passed.")
                        return True
                    else:
                        logger.warning(
                            "[WebSearchService] SearXNG responded but 'results' field is missing. "
                            "Check that JSON format is enabled in SearXNG settings."
                        )
                        return False
                elif resp.status_code == 403:
                    logger.warning(
                        "[WebSearchService] SearXNG returned 403. "
                        "JSON format may be disabled. Enable it via: "
                        "SearXNG → Settings → Formats → check 'json'."
                    )
                    return False
                else:
                    logger.warning(
                        f"[WebSearchService] SearXNG health check returned HTTP {resp.status_code}."
                    )
                    return False
        except Exception as exc:
            logger.warning(f"[WebSearchService] SearXNG health check failed: {exc}")
            return False

    @classmethod
    def search(
        cls,
        query: str,
        max_results: int = 5,
        page: int = 1,
        categories: Optional[str] = None,
        time_range: Optional[str] = None,
    ) -> List[SearchResult]:
        """
        Execute a web search via SearXNG and return normalised results.

        Args:
            query:       The search query string.
            max_results: Maximum number of results to return (SearXNG may return fewer).
            page:        SearXNG page number (1-based).
            categories:  Comma-separated SearXNG categories e.g. "general,it".
            time_range:  Optional time filter e.g. "year", "month", "week".

        Returns:
            List of SearchResult dicts.  Empty list on any failure (never raises).

        Raises:
            Nothing. All errors are logged and an empty list is returned so the
            calling research agent can decide whether to proceed without results.
        """
        try:
            base = cls._base_url()
        except SearXNGUnavailableError as exc:
            logger.error(f"[WebSearchService] Cannot search: {exc}")
            return []

        params: dict = {
            "q": query,
            "format": "json",
            "pageno": page,
        }
        if categories:
            params["categories"] = categories
        if time_range:
            params["time_range"] = time_range

        t_start = time.monotonic()
        try:
            with httpx.Client(
                timeout=httpx.Timeout(cls._CONNECT_TIMEOUT, read=cls._READ_TIMEOUT)
            ) as client:
                resp = client.get(f"{base}/search", params=params)

            elapsed_ms = int((time.monotonic() - t_start) * 1000)
            logger.info(
                f"[WebSearchService] GET {base}/search?q={query!r} "
                f"→ HTTP {resp.status_code} in {elapsed_ms}ms"
            )

            if resp.status_code == 403:
                logger.error(
                    "[WebSearchService] SearXNG returned 403 — JSON format is likely disabled. "
                    "Enable it via SearXNG → Settings → Formats → check 'json'."
                )
                return []

            resp.raise_for_status()

        except httpx.TimeoutException as exc:
            logger.warning(f"[WebSearchService] Timeout searching SearXNG for '{query}': {exc}")
            return []
        except httpx.HTTPStatusError as exc:
            logger.error(
                f"[WebSearchService] HTTP error from SearXNG for '{query}': {exc}"
            )
            return []
        except httpx.RequestError as exc:
            logger.error(
                f"[WebSearchService] Connection error reaching SearXNG for '{query}': {exc}"
            )
            return []

        try:
            data = resp.json()
        except Exception as exc:
            logger.error(
                f"[WebSearchService] Failed to parse SearXNG JSON response for '{query}': {exc}"
            )
            return []

        raw_results = data.get("results", [])
        if not raw_results:
            logger.info(f"[WebSearchService] SearXNG returned 0 results for '{query}'.")
            return []

        normalised: List[SearchResult] = []
        for item in raw_results[:max_results]:
            normalised.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    content=item.get("content", ""),
                    engine=item.get("engine") or item.get("engines", [None])[0],
                    score=item.get("score"),
                )
            )

        logger.info(
            f"[WebSearchService] Returned {len(normalised)} results for '{query}'."
        )
        return normalised
