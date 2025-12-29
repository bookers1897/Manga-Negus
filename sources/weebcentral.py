"""
================================================================================
MangaNegus v2.2 - WeebCentral Connector
================================================================================
WeebCentral (weebcentral.com) connector - successor to MangaSee/Manga4Life.

WeebCentral is the new platform by the creator of MangaSee, offering a large
library of manga with regular updates.

IMPLEMENTATION:
  - Based on Keiyoushi/Tachiyomi extension
  - Uses /search/data JSON endpoint for search
  - Uses /full-chapter-list for chapters
  - Uses /images endpoint for pages

NOTE: Requires proper headers to avoid Cloudflare protection.
================================================================================
"""

import re
import json
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin, quote

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

from .base import (
    BaseConnector, MangaResult, ChapterResult, PageResult, SourceStatus
)


class WeebCentralConnector(BaseConnector):
    """WeebCentral connector using their search API."""

    # =========================================================================
    # CONFIGURATION
    # =========================================================================

    id = "weebcentral"
    name = "WeebCentral"
    base_url = "https://weebcentral.com"
    icon = "🌐"

    rate_limit = 2.0  # Conservative rate limiting
    rate_limit_burst = 4
    request_timeout = 20

    supports_latest = True
    supports_popular = True
    requires_cloudflare = True  # Has Cloudflare but manageable

    languages = ["en"]

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    # =========================================================================
    # REQUEST HELPERS
    # =========================================================================

    def _headers(self, for_images: bool = False) -> Dict[str, str]:
        """Get request headers."""
        if for_images:
            return {
                "User-Agent": self.USER_AGENT,
                "Accept": "image/avif,image/webp,*/*",
                "Referer": self.base_url
            }
        return {
            "User-Agent": self.USER_AGENT,
            "Accept": "application/json, text/html, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": self.base_url
        }

    def _request_html(self, url: str) -> Optional[str]:
        """Fetch HTML with rate limiting."""
        if not self.session:
            return None

        self._wait_for_rate_limit()

        try:
            response = self.session.get(
                url,
                headers=self._headers(),
                timeout=self.request_timeout
            )

            if response.status_code == 200:
                if "cf-browser-verification" in response.text or "cf_clearance" in response.text:
                    self._handle_cloudflare()
                    return None
                self._handle_success()
                return response.text
            elif response.status_code == 403:
                self._handle_cloudflare()
                return None
            elif response.status_code == 429:
                self._handle_rate_limit(60)
                return None
            else:
                self._handle_error(f"HTTP {response.status_code}")
                return None

        except Exception as e:
            self._handle_error(str(e))
            return None

    def _request_json(self, url: str, params: Optional[Dict] = None) -> Optional[Any]:
        """Fetch JSON data with rate limiting."""
        if not self.session:
            return None

        self._wait_for_rate_limit()

        try:
            response = self.session.get(
                url,
                params=params,
                headers=self._headers(),
                timeout=self.request_timeout
            )

            if response.status_code == 200:
                self._handle_success()
                return response.json()
            elif response.status_code == 403:
                self._handle_cloudflare()
                return None
            elif response.status_code == 429:
                self._handle_rate_limit(60)
                return None
            else:
                self._handle_error(f"HTTP {response.status_code}")
                return None

        except Exception as e:
            self._handle_error(str(e))
            return None

    def _log(self, msg: str) -> None:
        """Log message."""
        try:
            from app import log
            log(msg)
        except:
            print(msg)

    # =========================================================================
    # PARSING HELPERS
    # =========================================================================

    def _clean_query(self, query: str) -> str:
        """Clean search query by removing special characters."""
        # Remove special characters that WeebCentral doesn't like
        return re.sub(r'[!#:()]', '', query)

    def _extract_chapter_num(self, text: str) -> str:
        """Extract chapter number from text."""
        match = re.search(r'[Cc]h(?:apter)?\.?\s*(\d+(?:\.\d+)?)', text)
        return match.group(1) if match else "0"

    # =========================================================================
    # PUBLIC API METHODS
    # =========================================================================

    def search(self, query: str, page: int = 1) -> List[MangaResult]:
        """Search WeebCentral for manga using their JSON API."""
        if not HAS_BS4:
            self._log("⚠️ BeautifulSoup not installed")
            return []

        self._log(f"🔍 Searching WeebCentral: {query}")

        # Clean the query
        clean_query = self._clean_query(query)

        # Calculate offset for pagination
        limit = 32
        offset = (page - 1) * limit

        # Use WeebCentral's search API
        params = {
            "text": clean_query,
            "limit": limit,
            "offset": offset
        }

        data = self._request_json(f"{self.base_url}/search/data", params)
        if not data or not isinstance(data, list):
            return []

        results = []
        for item in data[:20]:  # Limit to 20 results
            try:
                manga_id = item.get("slug", "")
                if not manga_id:
                    continue

                title = item.get("title", manga_id)
                cover = item.get("cover")
                if cover:
                    cover = urljoin(self.base_url, cover)

                manga_url = f"{self.base_url}/manga/{manga_id}"

                results.append(MangaResult(
                    id=manga_id,
                    title=title,
                    source=self.id,
                    cover_url=cover,
                    url=manga_url,
                    status=item.get("status", "").lower()
                ))
            except Exception:
                continue

        self._log(f"✅ Found {len(results)} results")
        return results

    def get_popular(self, page: int = 1) -> List[MangaResult]:
        """Get popular manga."""
        # WeebCentral doesn't have a specific popular endpoint
        # Use empty search with high limit to get popular
        if not HAS_BS4:
            return []

        limit = 32
        offset = (page - 1) * limit

        params = {
            "text": "",
            "limit": limit,
            "offset": offset
        }

        data = self._request_json(f"{self.base_url}/search/data", params)
        if not data or not isinstance(data, list):
            return []

        results = []
        for item in data[:20]:
            try:
                manga_id = item.get("slug", "")
                if not manga_id:
                    continue

                title = item.get("title", manga_id)
                cover = item.get("cover")
                if cover:
                    cover = urljoin(self.base_url, cover)

                results.append(MangaResult(
                    id=manga_id,
                    title=title,
                    source=self.id,
                    cover_url=cover,
                    url=f"{self.base_url}/manga/{manga_id}"
                ))
            except Exception:
                continue

        return results

    def get_latest(self, page: int = 1) -> List[MangaResult]:
        """Get recently updated manga."""
        return self.get_popular(page)  # Same endpoint

    def get_chapters(
        self,
        manga_id: str,
        language: str = "en"
    ) -> List[ChapterResult]:
        """Get chapter list for a manga."""
        if not HAS_BS4:
            return []

        self._log(f"📖 Fetching chapters from WeebCentral...")

        # Build full chapter list URL
        url = f"{self.base_url}/manga/{manga_id}/full-chapter-list"

        html = self._request_html(url)
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')

        # Find chapter links: div[x-data] > a
        chapter_links = soup.select('div[x-data] > a')

        results = []
        for link in chapter_links:
            try:
                chapter_url = link.get('href', '')
                if not chapter_url:
                    continue

                if not chapter_url.startswith('http'):
                    chapter_url = urljoin(self.base_url, chapter_url)

                # Get chapter text
                chapter_text = link.get_text(strip=True)
                chapter_num = self._extract_chapter_num(chapter_text)

                # Try to get date/time
                time_elem = link.select_one('time')
                date = time_elem.get('datetime') if time_elem else None

                results.append(ChapterResult(
                    id=chapter_url,
                    chapter=chapter_num,
                    title=chapter_text,
                    language="en",
                    published=date,
                    url=chapter_url,
                    source=self.id
                ))
            except Exception:
                continue

        # Sort by chapter number
        results.sort(key=lambda x: float(x.chapter) if x.chapter else 0)

        self._log(f"✅ Found {len(results)} chapters")
        return results

    def get_pages(self, chapter_id: str) -> List[PageResult]:
        """Get page images for a chapter."""
        if not HAS_BS4:
            return []

        # chapter_id is the full chapter URL
        # Append /images with parameters
        url = f"{chapter_id}/images"
        params = {
            "is_prev": "False",
            "reading_style": "long_strip"
        }

        # Build full URL with params
        param_str = "&".join([f"{k}={v}" for k, v in params.items()])
        full_url = f"{url}?{param_str}"

        html = self._request_html(full_url)
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')

        # Find all img elements
        images = soup.select('img')

        pages = []
        for i, img in enumerate(images):
            src = img.get('src', '') or img.get('data-src', '')

            if src:
                if not src.startswith('http'):
                    src = urljoin(self.base_url, src)

                pages.append(PageResult(
                    url=src,
                    index=i,
                    headers=self._headers(for_images=True),
                    referer=chapter_id
                ))

        return pages
