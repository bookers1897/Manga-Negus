"""
================================================================================
MangaNegus v3.1 - Base Metadata Provider
================================================================================
Abstract base class for all external metadata API providers.

Providers implement search and fetch operations for:
  - AniList (GraphQL)
  - MyAnimeList via Jikan (REST)
  - Kitsu (JSON:API)
  - Shikimori (REST)
  - MangaUpdates (REST)

Design follows Gemini's architecture with rate limiting and caching.
================================================================================
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict
import time
import asyncio
import logging
from datetime import datetime, timedelta

import httpx

from ..models import UnifiedMetadata, IDMapping


logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Token bucket rate limiter for API requests.

    Prevents exceeding provider rate limits:
      - AniList: 90/min
      - Jikan: 60/min (3/sec)
      - Kitsu: 60/min (conservative)
      - Shikimori: 300/min (5/sec)
      - MangaUpdates: 30/min (conservative)
    """

    def __init__(self, requests_per_minute: int):
        """
        Initialize rate limiter.

        Args:
            requests_per_minute: Maximum requests allowed per minute
        """
        self.requests_per_minute = requests_per_minute
        self.min_interval = 60.0 / requests_per_minute  # Seconds between requests
        self.last_request = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self):
        """Wait until a request slot is available."""
        async with self._lock:
            now = time.time()
            time_since_last = now - self.last_request

            if time_since_last < self.min_interval:
                wait_time = self.min_interval - time_since_last
                logger.debug(f"Rate limit: waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)

            self.last_request = time.time()


class BaseMetadataProvider(ABC):
    """
    Abstract base class for metadata providers.

    All providers must implement:
      - search_series(): Search by title
      - get_by_id(): Fetch by provider-specific ID

    Providers handle:
      - Rate limiting (token bucket)
      - Error handling with retries
      - Response parsing to UnifiedMetadata
      - Caching hints (TTL)
    """

    # Provider identification
    id: str = "base"
    name: str = "Base Provider"

    # API configuration
    base_url: str = ""
    api_version: str = "v1"

    # Rate limiting (requests per minute)
    rate_limit: int = 60

    # Request timeout (seconds)
    timeout: int = 10

    # Retry configuration
    max_retries: int = 3
    retry_delay: float = 1.0

    # User-Agent (some APIs require this)
    user_agent: str = "MangaNegus/3.1 (+https://github.com/bookers1897/Manga-Negus)"

    def __init__(self):
        """Initialize provider with rate limiter and HTTP client."""
        self.rate_limiter = RateLimiter(self.rate_limit)
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={
                    'User-Agent': self.user_agent,
                    'Accept': 'application/json'
                }
            )
        return self._client

    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> Dict:
        """
        Make rate-limited HTTP request with retries.

        Args:
            method: HTTP method (GET, POST)
            url: Full URL
            **kwargs: Additional arguments for httpx

        Returns:
            JSON response as dict

        Raises:
            httpx.HTTPError: On request failure after retries
        """
        client = await self._get_client()

        for attempt in range(self.max_retries):
            try:
                # Rate limit
                await self.rate_limiter.acquire()

                # Make request
                response = await client.request(method, url, **kwargs)
                response.raise_for_status()

                return response.json()

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:  # Rate limited
                    wait_time = self.retry_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(
                        f"{self.id}: Rate limited (429), waiting {wait_time}s"
                    )
                    await asyncio.sleep(wait_time)
                    continue
                elif e.response.status_code >= 500:  # Server error
                    if attempt < self.max_retries - 1:
                        logger.warning(
                            f"{self.id}: Server error ({e.response.status_code}), "
                            f"retry {attempt + 1}/{self.max_retries}"
                        )
                        await asyncio.sleep(self.retry_delay)
                        continue
                raise

            except httpx.RequestError as e:
                if attempt < self.max_retries - 1:
                    logger.warning(
                        f"{self.id}: Request error ({e}), "
                        f"retry {attempt + 1}/{self.max_retries}"
                    )
                    await asyncio.sleep(self.retry_delay)
                    continue
                raise

        # Should not reach here
        raise Exception(f"{self.id}: Max retries exceeded")

    # =========================================================================
    # ABSTRACT METHODS (must be implemented by providers)
    # =========================================================================

    @abstractmethod
    async def search_series(
        self,
        title: str,
        limit: int = 10
    ) -> List[UnifiedMetadata]:
        """
        Search for manga by title.

        Args:
            title: Manga title to search for
            limit: Maximum number of results

        Returns:
            List of UnifiedMetadata objects
        """
        pass

    @abstractmethod
    async def get_by_id(
        self,
        provider_id: str
    ) -> Optional[UnifiedMetadata]:
        """
        Get manga by provider-specific ID.

        Args:
            provider_id: ID in this provider's system

        Returns:
            UnifiedMetadata or None if not found
        """
        pass

    # =========================================================================
    # OPTIONAL METHODS (providers can override for optimization)
    # =========================================================================

    async def batch_get(
        self,
        provider_ids: List[str]
    ) -> List[UnifiedMetadata]:
        """
        Batch fetch multiple manga (for providers that support it).

        Default implementation: Sequential calls to get_by_id()
        Override for providers with batch APIs (like AniList GraphQL)

        Args:
            provider_ids: List of IDs to fetch

        Returns:
            List of UnifiedMetadata objects
        """
        results = []
        for provider_id in provider_ids:
            try:
                result = await self.get_by_id(provider_id)
                if result:
                    results.append(result)
            except Exception as e:
                logger.error(f"{self.id}: Batch get failed for {provider_id}: {e}")
                continue

        return results

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def normalize_title(self, title: str) -> str:
        """
        Normalize title for matching.

        Removes special characters, converts to lowercase, etc.

        Args:
            title: Original title

        Returns:
            Normalized title
        """
        import re

        # Remove special characters except spaces
        title = re.sub(r'[^\w\s]', '', title)

        # Convert to lowercase
        title = title.lower()

        # Collapse multiple spaces
        title = re.sub(r'\s+', ' ', title).strip()

        return title

    def get_cache_ttl(self, metadata: UnifiedMetadata) -> int:
        """
        Get recommended cache TTL for this metadata.

        Static data (titles, genres): 30 days
        Dynamic data (ratings): 24 hours
        Status (if finished): permanent

        Args:
            metadata: Metadata object

        Returns:
            TTL in seconds
        """
        from ..models import MangaStatus

        # Finished manga = static forever (30 days)
        if metadata.status == MangaStatus.FINISHED:
            return 30 * 24 * 3600  # 30 days

        # Releasing manga = check ratings daily
        elif metadata.status == MangaStatus.RELEASING:
            return 24 * 3600  # 24 hours

        # Default: 7 days
        else:
            return 7 * 24 * 3600  # 7 days

    def __repr__(self):
        return f"<{self.__class__.__name__}(id='{self.id}', rate_limit={self.rate_limit}/min)>"
