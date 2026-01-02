"""
================================================================================
MangaNegus v2.2 - MangaHere Connector
================================================================================
MangaHere (mangahere.cc) connector for scraping manga content.

MangaHere is a well-established manga reading website with a broad selection
of manga titles and a straightforward interface.

FEATURES:
  - Large manga library
  - Search functionality
  - Chapter listings
  - Image scraping

NOTE: This is a scraping-based connector.
================================================================================
"""

import re
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


class MangaHereConnector(BaseConnector):
    """MangaHere scraper connector."""

    # =========================================================================
    # CONFIGURATION
    # =========================================================================

    id = "mangahere"
    name = "MangaHere"
    base_url = "https://www.mangahere.cc"
    icon = "📕"
    
    # URL Detection patterns
    url_patterns = [
        r'https?://(?:www\.)?mangahere\.(?:cc|io)/manga/([a-z0-9_-]+)',  # e.g., /manga/naruto
    ]

    rate_limit = 2.0
    rate_limit_burst = 4
    request_timeout = 20

    supports_latest = True
    supports_popular = True
    requires_cloudflare = False

    languages = ["en"]

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    # =========================================================================
    # REQUEST HELPERS
    # =========================================================================

    def _headers(self) -> Dict[str, str]:
        """Get request headers."""
        return {
            "User-Agent": self.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
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

    def _log(self, msg: str) -> None:
        """Log message using the central source_log."""
        source_log(f"[{self.id}] {msg}")

    # =========================================================================
    # PARSING HELPERS
    # =========================================================================

    def _extract_chapter_num(self, text: str) -> str:
        """Extract chapter number from text."""
        match = re.search(r'[Cc]h(?:apter)?\.?\s*(\d+(?:\.\d+)?)', text)
        return match.group(1) if match else "0"

    # =========================================================================
    # PUBLIC API METHODS
    # =========================================================================

    def search(self, query: str, page: int = 1) -> List[MangaResult]:
        """Search MangaHere for manga."""
        if not HAS_BS4:
            self._log("⚠️ BeautifulSoup not installed")
            return []

        self._log(f"🔍 Searching MangaHere: {query}")

        # URL encode the query
        encoded_query = quote(query)
        url = f"{self.base_url}/search?name={encoded_query}&page={page}"

        html = self._request_html(url)
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')

        # Find manga items
        items = soup.select('.manga-list-4-item-container, .manga_list-sbs li')
        results = []

        for item in items[:20]:  # Limit to 20 results
            try:
                # Get link and title
                link = item.select_one('a.manga-list-4-item-title, a')
                if not link:
                    continue

                manga_url = link.get('href', '')
                if not manga_url.startswith('http'):
                    manga_url = urljoin(self.base_url, manga_url)

                title = link.get_text(strip=True) or link.get('title', 'Unknown')

                # Extract manga ID from URL
                manga_id = manga_url.rstrip('/').split('/')[-1]

                # Get cover
                img = item.select_one('img')
                cover = img.get('src', '') if img else None
                if cover and not cover.startswith('http'):
                    cover = urljoin(self.base_url, cover)

                results.append(MangaResult(
                    id=manga_id,
                    title=title,
                    source=self.id,
                    cover_url=cover,
                    url=manga_url
                ))
            except Exception as e:

                self._log(f"Failed to parse item: {e}")

                continue

        self._log(f"✅ Found {len(results)} results")
        return results

    def get_popular(self, page: int = 1) -> List[MangaResult]:
        """Get popular manga."""
        if not HAS_BS4:
            return []

        url = f"{self.base_url}/directory/{page}.htm?views.za"
        html = self._request_html(url)
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')
        items = soup.select('.manga-list-4-item-container, .directory_list li')

        results = []
        for item in items[:20]:
            try:
                link = item.select_one('a')
                if not link:
                    continue

                manga_url = link.get('href', '')
                if not manga_url.startswith('http'):
                    manga_url = urljoin(self.base_url, manga_url)

                title = link.get('title', '') or link.get_text(strip=True)
                manga_id = manga_url.rstrip('/').split('/')[-1]

                img = item.select_one('img')
                cover = img.get('src', '') if img else None
                if cover and not cover.startswith('http'):
                    cover = urljoin(self.base_url, cover)

                results.append(MangaResult(
                    id=manga_id,
                    title=title,
                    source=self.id,
                    cover_url=cover,
                    url=manga_url
                ))
            except Exception as e:

                self._log(f"Failed to parse item: {e}")

                continue

        return results

    def get_latest(self, page: int = 1) -> List[MangaResult]:
        """Get recently updated manga."""
        if not HAS_BS4:
            return []

        url = f"{self.base_url}/directory/{page}.htm?latest.za"
        html = self._request_html(url)
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')
        items = soup.select('.manga-list-4-item-container, .directory_list li')

        results = []
        for item in items[:20]:
            try:
                link = item.select_one('a')
                if not link:
                    continue

                manga_url = link.get('href', '')
                if not manga_url.startswith('http'):
                    manga_url = urljoin(self.base_url, manga_url)

                title = link.get('title', '') or link.get_text(strip=True)
                manga_id = manga_url.rstrip('/').split('/')[-1]

                img = item.select_one('img')
                cover = img.get('src', '') if img else None
                if cover and not cover.startswith('http'):
                    cover = urljoin(self.base_url, cover)

                results.append(MangaResult(
                    id=manga_id,
                    title=title,
                    source=self.id,
                    cover_url=cover,
                    url=manga_url
                ))
            except Exception as e:

                self._log(f"Failed to parse item: {e}")

                continue

        return results

    def get_chapters(
        self,
        manga_id: str,
        language: str = "en"
    ) -> List[ChapterResult]:
        """Get chapter list for a manga."""
        if not HAS_BS4:
            return []

        self._log(f"📖 Fetching chapters from MangaHere...")

        # Build manga URL
        if manga_id.startswith('http'):
            url = manga_id
        else:
            url = f"{self.base_url}/manga/{manga_id}"

        html = self._request_html(url)
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')

        # Find chapter list
        chapter_items = soup.select('.detail-main-list li, ul.chlist li')

        results = []
        for item in chapter_items:
            try:
                link = item.select_one('a')
                if not link:
                    continue

                chapter_url = link.get('href', '')
                if not chapter_url.startswith('http'):
                    chapter_url = urljoin(self.base_url, chapter_url)

                chapter_title = link.get_text(strip=True)
                chapter_num = self._extract_chapter_num(chapter_title)

                # Get date if available
                date_elem = item.select_one('.title2, .chapterdate')
                date = date_elem.get_text(strip=True) if date_elem else None

                results.append(ChapterResult(
                    id=chapter_url,
                    chapter=chapter_num,
                    title=chapter_title,
                    language="en",
                    published=date,
                    url=chapter_url,
                    source=self.id
                ))
            except Exception as e:

                self._log(f"Failed to parse item: {e}")

                continue

        # Sort by chapter number
        results.sort(key=lambda x: float(x.chapter) if x.chapter else 0)

        self._log(f"✅ Found {len(results)} chapters")
        return results

    def get_pages(self, chapter_id: str) -> List[PageResult]:
        """Get page images for a chapter."""
        if not HAS_BS4:
            return []

        # chapter_id is the full URL
        url = chapter_id

        html = self._request_html(url)
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')

        # Find page images
        images = soup.select('#viewer img, .reader-main-img')

        pages = []
        for i, img in enumerate(images):
            src = img.get('src', '') or img.get('data-src', '') or img.get('data-original', '')

            if src:
                if not src.startswith('http'):
                    src = urljoin(self.base_url, src)

                pages.append(PageResult(
                    url=src,
                    index=i,
                    headers={
                        "User-Agent": self.USER_AGENT,
                        "Referer": url
                    },
                    referer=url
                ))

        return pages
