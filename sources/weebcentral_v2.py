"""
================================================================================
MangaNegus v3.0 - WeebCentral Lua Adapter
================================================================================
WeebCentral adapter using curl_cffi to bypass Cloudflare.

WeebCentral has 700+ chapters for popular manga like Naruto, One Piece, etc.
Much better English support than MangaDex for licensed manga.

Uses curl_cffi with Chrome impersonation to bypass Cloudflare.
================================================================================
"""

import re
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin, quote

try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False
    print("WARNING: curl_cffi not installed. Run: pip install curl_cffi")

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

from .base import (
    BaseConnector,
    MangaResult,
    ChapterResult,
    PageResult,
    SourceStatus,
    source_log
)


class WeebCentralV2Connector(BaseConnector):
    """
    WeebCentral adapter with Cloudflare bypass using curl_cffi.

    Uses Chrome browser impersonation to bypass Cloudflare protection.
    """

    id = "weebcentral-v2"
    name = "WeebCentral V2"
    base_url = "https://weebcentral.com"
    icon = "🌐"
    
    # URL Detection patterns
    url_patterns = [
        r'https?://(?:www\.)?weebcentral\.com/series/([a-z0-9-]+)',  # e.g., /series/naruto-colored
    ]

    rate_limit = 2.0  # Increased for faster downloads
    rate_limit_burst = 5
    request_timeout = 30

    supports_latest = True
    supports_popular = True
    requires_cloudflare = False  # We bypass it!

    languages = ["en"]

    def __init__(self):
        """Initialize WeebCentral adapter (lazy initialization - no blocking calls)."""
        super().__init__()
        self._session = None
        self._initialized = False

    def _ensure_session(self) -> bool:
        """Lazy initialization - create session and get cookies on first use."""
        if self._initialized:
            return self._session is not None

        self._initialized = True

        if not HAS_CURL_CFFI:
            source_log(f"[{self.id}] curl_cffi not installed!")
            return False

        if not HAS_BS4:
            source_log(f"[{self.id}] BeautifulSoup not installed!")
            return False

        # Create curl_cffi session
        self._session = curl_requests.Session()

        # Get cookies on first request (lazy)
        try:
            self._session.get(
                f"{self.base_url}/search",
                impersonate="chrome120",
                timeout=self.request_timeout
            )
            source_log(f"[{self.id}] Initialized with Chrome impersonation (lazy)")
        except Exception as e:
            source_log(f"[{self.id}] Init error: {e}")

        return self._session is not None

    def _get(self, url: str, params: Dict = None, htmx: bool = False) -> Optional[str]:
        """Make GET request with Chrome impersonation."""
        if not self._ensure_session():
            return None

        self._wait_for_rate_limit()

        try:
            headers = {}
            if htmx:
                headers["HX-Request"] = "true"
                headers["HX-Current-URL"] = f"{self.base_url}/search"

            resp = self._session.get(
                url,
                params=params,
                headers=headers,
                impersonate="chrome120",
                timeout=self.request_timeout
            )

            if resp.status_code == 200:
                self._handle_success()
                return resp.text
            else:
                self._handle_error(f"HTTP {resp.status_code}")
                return None

        except Exception as e:
            self._handle_error(str(e))
            source_log(f"[{self.id}] Request error: {e}")
            return None

    def _pick_srcset_url(self, srcset: str) -> Optional[str]:
        """Pick a usable URL from a srcset string."""
        if not srcset:
            return None
        parts = [p.strip() for p in srcset.split(',') if p.strip()]
        if not parts:
            return None
        candidate = parts[-1].split()[0]
        return candidate or None

    def _normalize_cover(self, url: Optional[str]) -> Optional[str]:
        """Normalize cover URL to absolute https URL."""
        if not url:
            return None
        url = url.strip()
        if url.startswith('//'):
            url = f"https:{url}"
        return urljoin(self.base_url, url)

    def get_download_session(self):
        """Use curl_cffi session for downloads when available."""
        return getattr(self, "_session", None) or self.session

    def search(self, query: str, page: int = 1) -> List[MangaResult]:
        """Search WeebCentral for manga."""
        source_log(f"[{self.id}] Searching: {query}")

        # Use HTMX endpoint
        html = self._get(
            f"{self.base_url}/search/data",
            params={"text": query, "display_mode": "Full Display"},
            htmx=True
        )

        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')
        results = []
        seen = set()

        # Find series links
        for link in soup.select('a[href*="/series/"]'):
            href = link.get('href', '')

            # Extract series ID and slug
            match = re.search(r'/series/([^/]+)/([^/]+)', href)
            if not match:
                continue

            series_id = match.group(1)
            if series_id in seen:
                continue
            seen.add(series_id)

            slug = match.group(2)

            # Get title from img alt
            img = link.select_one('img')
            title = img.get('alt', '').replace(' cover', '') if img else slug.replace('-', ' ').title()

            # Get cover
            picture = link.select_one('picture source')
            cover = self._pick_srcset_url(picture.get('srcset', '')) if picture else None
            if not cover and img:
                cover = img.get('data-src') or img.get('data-lazy-src') or img.get('src')
            cover = self._normalize_cover(cover)

            if not href.startswith("http"):
                href = urljoin(self.base_url, href)

            results.append(MangaResult(
                id=series_id,
                title=title,
                source=self.id,
                cover_url=cover,
                url=href
            ))

        source_log(f"[{self.id}] Found {len(results)} results")
        return results

    def get_popular(self, page: int = 1) -> List[MangaResult]:
        """Get popular manga (empty search returns popular)."""
        return self.search("", page)

    def get_latest(self, page: int = 1) -> List[MangaResult]:
        """Get latest updates."""
        return self.search("", page)

    def get_chapters(
        self,
        manga_id: str,
        language: str = "en"
    ) -> List[ChapterResult]:
        """Get chapter list for a manga."""
        source_log(f"[{self.id}] Getting chapters for: {manga_id}")

        # Get full chapter list page
        html = self._get(f"{self.base_url}/series/{manga_id}/full-chapter-list")

        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')
        results = []

        # Find chapter links
        for link in soup.select('a[href*="/chapters/"]'):
            href = link.get('href', '')

            # Extract chapter ID
            ch_match = re.search(r'/chapters/([^/]+)', href)
            if not ch_match:
                continue

            chapter_id = ch_match.group(1)

            # Get chapter text and extract number
            text = link.get_text(strip=True)
            ch_num_match = re.search(r'[Cc]hapter\s*(\d+(?:\.\d+)?)', text)
            chapter_num = ch_num_match.group(1) if ch_num_match else "0"

            # Get date if available
            time_el = link.select_one('time')
            date = time_el.get('datetime') if time_el else None

            results.append(ChapterResult(
                id=chapter_id,
                chapter=chapter_num,
                title=text.split('Last Read')[0].strip(),  # Remove "Last Read" text
                language="en",
                published=date,
                url=href,
                source=self.id
            ))

        # Sort by chapter number (descending by default, we'll reverse for ascending)
        results.sort(key=lambda x: float(x.chapter) if x.chapter.replace('.', '').isdigit() else 0)

        source_log(f"[{self.id}] Found {len(results)} chapters")
        return results

    def get_pages(self, chapter_id: str) -> List[PageResult]:
        """Get page images for a chapter."""
        source_log(f"[{self.id}] Getting pages for: {chapter_id}")

        # Build chapter URL
        if chapter_id.startswith('http'):
            url = chapter_id
        else:
            url = f"{self.base_url}/chapters/{chapter_id}/images"

        # Add reading style parameter
        if '?' not in url:
            url += "?reading_style=long_strip"
        else:
            url += "&reading_style=long_strip"

        html = self._get(url)

        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')
        pages = []

        # Find all page images (hosted on planeptune.us or other CDNs)
        for i, img in enumerate(soup.select('img')):
            src = img.get('src') or img.get('data-src')
            alt = img.get('alt', '')

            # Only include actual page images (have "Page" in alt or are from CDN)
            if src and ('planeptune' in src or 'Page' in alt or '/manga/' in src):
                if not src.startswith('http'):
                    src = urljoin(self.base_url, src)

                pages.append(PageResult(
                    url=src,
                    index=i,
                    headers={"Referer": self.base_url},
                    referer=self.base_url
                ))

        source_log(f"[{self.id}] Found {len(pages)} pages")
        return pages
