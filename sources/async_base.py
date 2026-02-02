"""
================================================================================
MangaNegus v2.3 - Async Base Connector
================================================================================
Base class for async manga source connectors using curl_cffi.

curl_cffi provides industry-standard Cloudflare TLS fingerprint bypass by
impersonating real browser fingerprints at the C level.
================================================================================
"""

import asyncio
import os
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from enum import Enum

# Import sync versions for fallback
from .base import MangaResult, ChapterResult, PageResult, SourceStatus

# Try to import curl_cffi
try:
    from curl_cffi.requests import AsyncSession
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False
    AsyncSession = None


class AsyncRateLimiter:
    """Async rate limiter with human-like jitter."""

    def __init__(self, requests_per_second: float = 2.0):
        self.delay = 1.0 / requests_per_second
        self.lock = asyncio.Lock()
        self.last_request = 0.0

    async def wait(self) -> None:
        async with self.lock:
            now = time.time()
            wait_time = self.last_request + self.delay - now
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            self.last_request = time.time() + random.uniform(0.1, 0.5)


class AsyncBaseConnector(ABC):
    """
    Async base class for manga source connectors.

    Uses curl_cffi with browser impersonation for Cloudflare bypass.
    All methods are async for maximum performance.
    """

    # Source identification
    id: str = "async_base"
    name: str = "Async Base"
    base_url: str = ""
    icon: str = ""

    # Rate limiting
    rate_limit: float = 2.0  # Requests per second
    rate_limit_burst: int = 5
    request_timeout: float = 30.0
    max_retries: int = 2
    backoff_base: float = 2.0
    backoff_max: float = 30.0

    # Features
    supports_latest: bool = False
    supports_popular: bool = False
    requires_cloudflare: bool = False

    # Languages supported
    languages: List[str] = ["en"]

    # Browser to impersonate (chrome110, chrome120, safari15_3, etc.)
    impersonate: str = "chrome120"

    def __init__(self):
        """Initialize async connector."""
        self._session: Optional[AsyncSession] = None
        self._limiter = AsyncRateLimiter(self.rate_limit)
        self._status = SourceStatus.ONLINE
        self._error_count = 0
        self._last_error = None
        self._initialized = False
        self._max_retries = int(os.environ.get("ASYNC_SCRAPER_MAX_RETRIES", str(self.max_retries)))
        self._backoff_base = float(os.environ.get("ASYNC_SCRAPER_BACKOFF_BASE", str(self.backoff_base)))
        self._backoff_max = float(os.environ.get("ASYNC_SCRAPER_BACKOFF_MAX", str(self.backoff_max)))

    async def _get_session(self) -> Optional[AsyncSession]:
        """Get or create curl_cffi AsyncSession."""
        if not HAS_CURL_CFFI:
            self._log("curl_cffi not installed - using sync fallback")
            return None

        if self._session is None:
            self._session = AsyncSession(impersonate=self.impersonate)
            self._initialized = True

        return self._session

    async def close(self) -> None:
        """Close the session."""
        if self._session:
            await self._session.close()
            self._session = None
            self._initialized = False

    async def _get(
        self,
        url: str,
        params: Optional[Dict] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Optional[Any]:
        """
        Make a GET request with rate limiting and Cloudflare bypass.

        Args:
            url: URL to fetch
            params: Query parameters
            headers: Additional headers

        Returns:
            Response object or None on failure
        """
        session = await self._get_session()
        if not session:
            return None

        # Build headers
        request_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": self.base_url,
        }
        if headers:
            request_headers.update(headers)

        for attempt in range(self._max_retries + 1):
            await self._limiter.wait()
            try:
                response = await session.get(
                    url,
                    params=params,
                    headers=request_headers,
                    timeout=self.request_timeout
                )
            except Exception as e:
                self._handle_error(str(e))
                if attempt < self._max_retries:
                    await asyncio.sleep(self._get_retry_delay(None, attempt))
                    continue
                return None

            if response.status_code == 200:
                self._handle_success()
                return response

            if response.status_code in [403, 429]:
                retry_after = response.headers.get("Retry-After")
                retry_after_val = None
                try:
                    retry_after_val = float(retry_after)
                except (TypeError, ValueError):
                    retry_after_val = None
                self._log(f"Rate limited or blocked ({response.status_code})")
                self._handle_rate_limit(int(retry_after_val or 30))
                if attempt < self._max_retries:
                    await asyncio.sleep(self._get_retry_delay(response, attempt))
                    continue
                return None

            if response.status_code >= 500:
                self._log(f"Server error ({response.status_code})")
                if attempt < self._max_retries:
                    await asyncio.sleep(self._get_retry_delay(response, attempt))
                    continue
                return None

            self._handle_error(f"HTTP {response.status_code}")
            return None

        return None

    def _get_retry_delay(self, response, attempt: int) -> float:
        """Compute retry delay with backoff and jitter."""
        delay = min(self._backoff_base * (2 ** attempt), self._backoff_max)
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            try:
                retry_after_val = float(retry_after)
            except (TypeError, ValueError):
                retry_after_val = None
            if retry_after_val is not None:
                delay = max(delay, retry_after_val)
        jitter = random.uniform(0.0, 0.35)
        return min(delay + jitter, self._backoff_max)

    async def _get_json(
        self,
        url: str,
        params: Optional[Dict] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Optional[Dict]:
        """Make a GET request and parse JSON response."""
        json_headers = {"Accept": "application/json"}
        if headers:
            json_headers.update(headers)

        response = await self._get(url, params, json_headers)
        if response:
            try:
                return response.json()
            except Exception:
                return None
        return None

    async def _get_html(
        self,
        url: str,
        params: Optional[Dict] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Optional[str]:
        """Make a GET request and return HTML text."""
        response = await self._get(url, params, headers)
        if response:
            return response.text
        return None

    # =========================================================================
    # STATUS MANAGEMENT
    # =========================================================================

    def _handle_success(self) -> None:
        """Handle successful request."""
        self._error_count = 0
        self._status = SourceStatus.ONLINE

    def _handle_error(self, error: str) -> None:
        """Handle request error."""
        self._error_count += 1
        self._last_error = error
        if self._error_count >= 5:
            self._status = SourceStatus.OFFLINE

    def _handle_rate_limit(self, retry_after: int = 30) -> None:
        """Handle rate limit response."""
        self._status = SourceStatus.RATE_LIMITED

    def _log(self, msg: str) -> None:
        """Log a message."""
        from sources.base import source_log
        source_log(msg)

    @property
    def is_available(self) -> bool:
        """Check if source is available."""
        return self._status == SourceStatus.ONLINE

    # =========================================================================
    # ABSTRACT METHODS
    # =========================================================================

    @abstractmethod
    async def search(self, query: str, page: int = 1) -> List[MangaResult]:
        """Search for manga."""
        pass

    @abstractmethod
    async def get_chapters(
        self,
        manga_id: str,
        language: str = "en"
    ) -> List[ChapterResult]:
        """Get chapters for a manga."""
        pass

    @abstractmethod
    async def get_pages(self, chapter_id: str) -> List[PageResult]:
        """Get page images for a chapter."""
        pass

    async def get_popular(self, page: int = 1) -> List[MangaResult]:
        """Get popular manga (optional)."""
        return []

    async def get_latest(self, page: int = 1) -> List[MangaResult]:
        """Get latest updates (optional)."""
        return []

    async def get_manga_details(self, manga_id: str) -> Optional[MangaResult]:
        """Get manga details (optional)."""
        return None


def run_async(coro):
    """Run an async coroutine from sync code."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're in an async context, create a task
            return asyncio.ensure_future(coro)
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        # No event loop, create one
        return asyncio.run(coro)
