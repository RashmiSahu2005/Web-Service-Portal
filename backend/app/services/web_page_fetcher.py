"""
web_page_fetcher.py
-------------------
Bounded web page fetcher for the Installation Research Agent.

Fetches selected search result URLs and extracts readable text.
Used to get authoritative installation documentation when
search result snippets are insufficient.

Constraints:
- MAX_PAGE_FETCHES: at most 3 pages fetched per research call
- PAGE_TIMEOUT: 8 seconds per page
- MAX_PAGE_CHARS: 12,000 characters returned per page
- No recursive crawling
- Only HTTP/HTTPS URLs accepted
"""

import re
from typing import Optional
from urllib.parse import urlparse

import httpx
from app.core.logger import logger

# Hard limits — do not increase without review
MAX_PAGE_FETCHES: int = 3
PAGE_TIMEOUT_SECONDS: float = 8.0
MAX_PAGE_CHARS: int = 12_000

# User-agent that looks like a normal browser to avoid bot-detection
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def _is_valid_url(url: str) -> bool:
    """Return True only for http/https URLs with a valid hostname."""
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def _extract_text_simple(html: str) -> str:
    """
    Very lightweight HTML-to-text: removes script/style blocks and HTML tags.
    Falls back gracefully if BeautifulSoup is not installed.
    """
    try:
        from bs4 import BeautifulSoup  # type: ignore
        soup = BeautifulSoup(html, "html.parser")

        # Remove boilerplate elements
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            tag.decompose()

        text = soup.get_text(separator="\n")
    except ImportError:
        # Fallback: regex strip
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"&[a-z]+;", " ", text)

    # Collapse excessive whitespace
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)


def fetch_page(url: str) -> Optional[str]:
    """
    Fetch a single page and return bounded extracted text.

    Returns:
        Extracted text string (up to MAX_PAGE_CHARS), or None on any failure.

    Never raises — all errors are logged and None is returned.
    """
    if not _is_valid_url(url):
        logger.warning(f"[WebPageFetcher] Rejected non-HTTP URL: {url!r}")
        return None

    try:
        with httpx.Client(
            timeout=httpx.Timeout(PAGE_TIMEOUT_SECONDS),
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            resp = client.get(url)

        if resp.status_code != 200:
            logger.warning(
                f"[WebPageFetcher] HTTP {resp.status_code} fetching {url}"
            )
            return None

        content_type = resp.headers.get("content-type", "")
        if "html" not in content_type and "text" not in content_type:
            logger.info(
                f"[WebPageFetcher] Skipping non-HTML content ({content_type}) for {url}"
            )
            return None

        text = _extract_text_simple(resp.text)
        if not text:
            return None

        # Bound the output
        if len(text) > MAX_PAGE_CHARS:
            text = text[:MAX_PAGE_CHARS] + f"\n\n[...content truncated at {MAX_PAGE_CHARS} chars]"

        logger.info(
            f"[WebPageFetcher] Fetched {len(text)} chars from {url}"
        )
        return text

    except httpx.TimeoutException:
        logger.warning(f"[WebPageFetcher] Timeout fetching {url}")
        return None
    except httpx.RequestError as exc:
        logger.warning(f"[WebPageFetcher] Request error fetching {url}: {exc}")
        return None
    except Exception as exc:
        logger.error(f"[WebPageFetcher] Unexpected error fetching {url}: {exc}")
        return None


def fetch_pages(urls: list[str], max_fetches: int = MAX_PAGE_FETCHES) -> dict[str, str]:
    """
    Fetch up to `max_fetches` pages from the provided URL list.

    Returns:
        Dict mapping url → extracted_text for successful fetches.
        Failed fetches are silently omitted.
    """
    results: dict[str, str] = {}
    fetched = 0

    for url in urls:
        if fetched >= max_fetches:
            logger.info(
                f"[WebPageFetcher] Reached max_fetches={max_fetches}, stopping early."
            )
            break

        text = fetch_page(url)
        if text:
            results[url] = text
            fetched += 1

    return results
