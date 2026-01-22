"""
================================================================================
MangaNegus v2.3 - Async Utilities
================================================================================
Async rate limiting and download utilities for massive speed improvements.

Features:
  - Async rate limiter with human-like jitter
  - Semaphore-based concurrent download limiting
  - curl_cffi session management with TLS fingerprint bypass
  - Stealth headers with SessionFingerprint
================================================================================
"""

import asyncio
import random
import time
from typing import Optional, Dict, Any, List

try:
    from .stealth_headers import SessionFingerprint, human_like_jitter
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False
    SessionFingerprint = None
    human_like_jitter = lambda x=0.5: random.uniform(0.3, 0.7)


class AsyncRateLimiter:
    """
    Async rate limiter with human-like jitter.

    Limits requests to X per second while adding subtle timing variations
    to appear more human-like and avoid bot detection.
    """

    def __init__(self, requests_per_second: float = 2.0):
        """
        Initialize rate limiter.

        Args:
            requests_per_second: Maximum requests per second allowed
        """
        self.delay = 1.0 / requests_per_second
        self.lock = asyncio.Lock()
        self.last_request = 0.0

    async def wait(self) -> None:
        """Wait for rate limit slot to become available."""
        async with self.lock:
            now = time.time()
            wait_time = self.last_request + self.delay - now
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            # Add subtle jitter to look human
            self.last_request = time.time() + random.uniform(0.1, 0.5)

    def set_rate(self, requests_per_second: float) -> None:
        """Update the rate limit."""
        self.delay = 1.0 / requests_per_second


class AsyncDownloadManager:
    """
    Manages concurrent async downloads with rate limiting.

    Uses semaphores to limit concurrent connections and prevent bans.
    Includes stealth headers for bot detection avoidance.
    """

    def __init__(
        self,
        max_concurrent: int = 5,
        requests_per_second: float = 2.0
    ):
        """
        Initialize download manager.

        Args:
            max_concurrent: Maximum concurrent downloads (default 5)
            requests_per_second: Rate limit for requests
        """
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.limiter = AsyncRateLimiter(requests_per_second)
        self._session = None
        # Stealth fingerprint for consistent browser identity
        self._fingerprint = SessionFingerprint() if HAS_STEALTH else None

    async def get_session(self):
        """Get or create curl_cffi AsyncSession."""
        if self._session is None:
            try:
                from curl_cffi.requests import AsyncSession
                self._session = AsyncSession(impersonate="chrome120")
            except ImportError:
                # Fallback to aiohttp if curl_cffi not available
                import aiohttp
                self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Close the session."""
        if self._session:
            await self._session.close()
            self._session = None

    async def fetch(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 30.0
    ) -> Optional[bytes]:
        """
        Fetch content from URL with rate limiting.

        Args:
            url: URL to fetch
            headers: Optional request headers
            timeout: Request timeout in seconds

        Returns:
            Response content as bytes, or None on failure
        """
        async with self.semaphore:
            await self.limiter.wait()

            try:
                session = await self.get_session()

                # curl_cffi style
                if hasattr(session, 'get'):
                    response = await session.get(
                        url,
                        headers=headers,
                        timeout=timeout
                    )

                    if response.status_code in [403, 429]:
                        print(f"[async] Rate limited on {url[:50]}...")
                        await asyncio.sleep(5)
                        return None

                    if response.status_code == 200:
                        return response.content

                    return None

                # aiohttp style fallback
                else:
                    async with session.get(url, headers=headers, timeout=timeout) as response:
                        if response.status in [403, 429]:
                            print(f"[async] Rate limited on {url[:50]}...")
                            await asyncio.sleep(5)
                            return None

                        if response.status == 200:
                            return await response.read()

                        return None

            except Exception as e:
                print(f"[async] Fetch error: {e}")
                return None

    async def fetch_json(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 30.0
    ) -> Optional[Dict[str, Any]]:
        """Fetch JSON from URL."""
        async with self.semaphore:
            await self.limiter.wait()

            try:
                session = await self.get_session()

                if hasattr(session, 'get'):
                    response = await session.get(url, headers=headers, timeout=timeout)
                    if response.status_code == 200:
                        return response.json()
                    return None
                else:
                    async with session.get(url, headers=headers, timeout=timeout) as response:
                        if response.status == 200:
                            return await response.json()
                        return None

            except Exception as e:
                print(f"[async] JSON fetch error: {e}")
                return None

    async def download_pages(
        self,
        pages: list,
        output_dir: str,
        referer: Optional[str] = None
    ) -> int:
        """
        Download multiple pages concurrently.

        Args:
            pages: List of PageResult objects
            output_dir: Directory to save files
            referer: Optional referer header

        Returns:
            Number of successfully downloaded pages
        """
        import os
        import aiofiles

        os.makedirs(output_dir, exist_ok=True)

        async def download_page(page) -> bool:
            """Download a single page."""
            try:
                # Build headers using stealth fingerprint
                if self._fingerprint:
                    headers = self._fingerprint.get_image_headers(referer)
                else:
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Accept": "image/*,*/*;q=0.8",
                    }
                    if referer:
                        headers["Referer"] = referer
                # Merge page-specific headers
                if hasattr(page, 'headers') and page.headers:
                    headers.update(page.headers)

                # Fetch content
                content = await self.fetch(page.url, headers=headers)
                if not content:
                    return False

                # Determine extension
                ext = page.url.split('.')[-1].split('?')[0].lower()
                if ext not in ['jpg', 'jpeg', 'png', 'webp', 'gif']:
                    ext = 'jpg'

                # Save file
                filepath = os.path.join(output_dir, f"{page.index:03d}.{ext}")
                async with aiofiles.open(filepath, 'wb') as f:
                    await f.write(content)

                return True

            except Exception as e:
                print(f"[async] Page download error: {e}")
                return False

        # Fire all downloads concurrently
        tasks = [download_page(page) for page in pages]
        results = await asyncio.gather(*tasks)

        return sum(1 for r in results if r)


# Global download manager instance
_download_manager: Optional[AsyncDownloadManager] = None


def get_download_manager(
    max_concurrent: int = 5,
    requests_per_second: float = 2.0
) -> AsyncDownloadManager:
    """Get or create global download manager."""
    global _download_manager
    if _download_manager is None:
        _download_manager = AsyncDownloadManager(max_concurrent, requests_per_second)
    return _download_manager


async def async_download_chapter(
    pages: list,
    output_dir: str,
    referer: Optional[str] = None,
    max_concurrent: int = 5
) -> int:
    """
    Convenience function to download a chapter asynchronously.

    Args:
        pages: List of PageResult objects
        output_dir: Directory to save files
        referer: Optional referer header
        max_concurrent: Max concurrent downloads

    Returns:
        Number of successfully downloaded pages
    """
    manager = get_download_manager(max_concurrent=max_concurrent)
    return await manager.download_pages(pages, output_dir, referer)


def download_chapter_sync(
    pages: list,
    output_dir: str,
    referer: Optional[str] = None,
    max_concurrent: int = 5
) -> int:
    """
    Synchronous wrapper for async chapter download.

    Use this from synchronous Flask routes.
    """
    return asyncio.run(async_download_chapter(pages, output_dir, referer, max_concurrent))
