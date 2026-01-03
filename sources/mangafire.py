"""
================================================================================
MangaNegus v2.3 - MangaFire Connector (with Cloudflare bypass)
================================================================================
MangaFire (mangafire.to) connector with cloudscraper for Cloudflare bypass.

FEATURES:
  - Cloudflare bypass using cloudscraper
  - Search functionality
  - Popular/trending manga
  - Latest updates
  - Chapter downloads
================================================================================
"""

import re
import time
import json
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin, quote

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

try:
    import cloudscraper
    HAS_CLOUDSCRAPER = True
except ImportError:
    HAS_CLOUDSCRAPER = False

from .base import (
    BaseConnector, MangaResult, ChapterResult, PageResult, SourceStatus
)


class MangaFireConnector(BaseConnector):
    """MangaFire scraper with Cloudflare bypass."""

    # =========================================================================
    # CONFIGURATION
    # =========================================================================

    id = "mangafire"
    name = "MangaFire"
    base_url = "https://mangafire.to"
    icon = "🔥"
    
    # URL Detection patterns
    url_patterns = [
        r'https?://(?:www\.)?mangafire\.to/manga/([a-z0-9.-]+)',  # e.g., /manga/naruto.4m
        r'https?://(?:www\.)?mangafire\.to/read/([a-z0-9.-]+)',   # e.g., /read/naruto.4m
    ]

    rate_limit = 2.0
    rate_limit_burst = 4
    request_timeout = 30

    supports_latest = True
    supports_popular = True
    requires_cloudflare = True  # Uses Cloudflare

    languages = ["en"]

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self):
        super().__init__()
        self._scraper = None
        self._init_scraper()

    def _init_scraper(self):
        """Initialize cloudscraper session."""
        if HAS_CLOUDSCRAPER:
            try:
                self._scraper = cloudscraper.create_scraper(
                    browser={
                        'browser': 'chrome',
                        'platform': 'windows',
                        'mobile': False
                    },
                    delay=5
                )
                self._log("✅ MangaFire Cloudflare bypass initialized")
            except Exception as e:
                self._log(f"⚠️ Failed to initialize cloudscraper: {e}")
                self._scraper = None
        else:
            self._log("⚠️ cloudscraper not installed. Run: pip install cloudscraper")

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

    def _request_html(self, url: str, retries: int = 3) -> Optional[str]:
        """Fetch HTML with Cloudflare bypass and rate limiting."""
        # Use cloudscraper if available, fall back to regular session
        session = self._scraper or self.session
        if not session:
            return None
        if self.requires_cloudflare and not self._scraper:
            self._handle_cloudflare()
            self._log("⚠️ MangaFire requires cloudscraper for access")
            return None

        self._wait_for_rate_limit()

        for attempt in range(retries):
            try:
                response = session.get(
                    url,
                    headers=self._headers(),
                    timeout=self.request_timeout
                )

                if response.status_code == 200:
                    # Check if we hit Cloudflare challenge page
                    if 'cf-browser-verification' in response.text or 'challenge-form' in response.text:
                        if attempt < retries - 1:
                            self._log(f"⚠️ Cloudflare challenge detected, retrying...")
                            time.sleep(5)
                            continue
                        self._handle_cloudflare()
                        return None

                    self._handle_success()
                    return response.text

                elif response.status_code == 403:
                    if attempt < retries - 1:
                        self._log(f"⚠️ 403 error, retrying in 5s...")
                        time.sleep(5)
                        continue
                    self._handle_cloudflare()
                    return None

                elif response.status_code == 429:
                    self._handle_rate_limit(60)
                    return None

                else:
                    if attempt < retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    self._handle_error(f"HTTP {response.status_code}")
                    return None

            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                self._handle_error(str(e))
                return None

        return None

    def _request_json(self, url: str) -> Optional[Dict]:
        """Fetch JSON with Cloudflare bypass."""
        session = self._scraper or self.session
        if not session:
            return None
        if self.requires_cloudflare and not self._scraper:
            self._handle_cloudflare()
            self._log("⚠️ MangaFire requires cloudscraper for access")
            return None

        self._wait_for_rate_limit()

        try:
            response = session.get(
                url,
                headers={**self._headers(), "Accept": "application/json"},
                timeout=self.request_timeout
            )

            if response.status_code == 200:
                self._handle_success()
                return response.json()

            return None

        except Exception as e:
            self._handle_error(str(e))
            return None

    def _log(self, msg: str) -> None:
        """Log message."""
        from sources.base import source_log
        source_log(msg)

    def get_download_session(self):
        """Prefer cloudscraper session for downloads."""
        return self._scraper or self.session

    # =========================================================================
    # PARSING HELPERS
    # =========================================================================

    def _extract_chapter_num(self, text: str) -> str:
        """Extract chapter number from text."""
        match = re.search(r'[Cc]h(?:apter)?\.?\s*(\d+(?:\.\d+)?)', text)
        return match.group(1) if match else "0"

    def _extract_manga_id(self, url: str) -> str:
        """Extract manga ID from URL."""
        # MangaFire URLs: /manga/title.id or /read/title.id/chapter
        parts = url.rstrip('/').split('/')
        for part in reversed(parts):
            if '.' in part:
                return part
        return parts[-1] if parts else ""

    # =========================================================================
    # PUBLIC API METHODS
    # =========================================================================

    def search(self, query: str, page: int = 1) -> List[MangaResult]:
        """Search MangaFire for manga."""
        if not HAS_BS4:
            self._log("⚠️ BeautifulSoup not installed")
            return []

        self._log(f"🔍 Searching MangaFire: {query}")

        encoded_query = quote(query)
        url = f"{self.base_url}/filter?keyword={encoded_query}&page={page}"

        html = self._request_html(url)
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')

        # MangaFire uses .unit class for manga items
        items = soup.select('.unit, .original.card-lg .inner, div.item')
        results = []

        for item in items[:20]:
            try:
                # Get link - poster or first anchor
                link = item.select_one('a.poster, a[href*="/manga/"]')
                if not link:
                    continue

                manga_url = link.get('href', '')
                if not manga_url.startswith('http'):
                    manga_url = urljoin(self.base_url, manga_url)

                manga_id = self._extract_manga_id(manga_url)

                # Get title
                title_elem = item.select_one('.info .name a, .info a, h3 a, .name')
                title = title_elem.get_text(strip=True) if title_elem else manga_id.split('.')[0].replace('-', ' ').title()

                # Get cover
                img = item.select_one('img')
                cover = None
                if img:
                    cover = img.get('src') or img.get('data-src')
                    if cover and not cover.startswith('http'):
                        cover = urljoin(self.base_url, cover)

                # Get type/status
                type_elem = item.select_one('.type, .status')
                status = type_elem.get_text(strip=True).lower() if type_elem else None

                results.append(MangaResult(
                    id=manga_id,
                    title=title,
                    source=self.id,
                    cover_url=cover,
                    status=status,
                    url=manga_url
                ))
            except Exception as e:
                continue

        self._log(f"✅ Found {len(results)} results")
        return results

    def get_popular(self, page: int = 1) -> List[MangaResult]:
        """Get popular manga."""
        if not HAS_BS4:
            return []

        url = f"{self.base_url}/filter?sort=most_viewed&page={page}"
        html = self._request_html(url)
        if not html:
            return []

        return self._parse_manga_list(html)

    def get_latest(self, page: int = 1) -> List[MangaResult]:
        """Get recently updated manga."""
        if not HAS_BS4:
            return []

        url = f"{self.base_url}/filter?sort=recently_updated&page={page}"
        html = self._request_html(url)
        if not html:
            return []

        return self._parse_manga_list(html)

    def _parse_manga_list(self, html: str) -> List[MangaResult]:
        """Parse manga list from HTML."""
        soup = BeautifulSoup(html, 'html.parser')
        items = soup.select('.unit, .original.card-lg .inner, div.item')

        results = []
        for item in items[:20]:
            try:
                link = item.select_one('a.poster, a[href*="/manga/"]')
                if not link:
                    continue

                manga_url = link.get('href', '')
                if not manga_url.startswith('http'):
                    manga_url = urljoin(self.base_url, manga_url)

                manga_id = self._extract_manga_id(manga_url)

                title_elem = item.select_one('.info .name a, .info a, h3 a, .name')
                title = title_elem.get_text(strip=True) if title_elem else manga_id.split('.')[0].replace('-', ' ').title()

                img = item.select_one('img')
                cover = None
                if img:
                    cover = img.get('src') or img.get('data-src')
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

        self._log(f"📖 Fetching chapters from MangaFire...")

        # Build manga URL
        if manga_id.startswith('http'):
            url = manga_id
            manga_id = self._extract_manga_id(manga_id)
        else:
            url = f"{self.base_url}/manga/{manga_id}"

        html = self._request_html(url)
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')

        # MangaFire chapter list - try multiple selectors
        chapter_items = soup.select('ul.chapter-list li, .list-body .item, div.chapter-item, .episodes-ul li')

        # If no chapters found, try the API endpoint
        if not chapter_items:
            # Extract numeric ID from manga_id
            numeric_id = manga_id.split('.')[-1] if '.' in manga_id else manga_id
            api_url = f"{self.base_url}/ajax/manga/{numeric_id}/chapter/en"
            data = self._request_json(api_url)
            if data and 'result' in data:
                # Parse the HTML from API response
                soup = BeautifulSoup(data['result'], 'html.parser')
                chapter_items = soup.select('li, a.item')

        results = []
        for item in chapter_items:
            try:
                link = item if item.name == 'a' else item.select_one('a')
                if not link:
                    continue

                chapter_url = link.get('href', '')
                if not chapter_url:
                    # Try data-id attribute
                    data_id = link.get('data-id') or item.get('data-id')
                    if data_id:
                        chapter_url = f"{self.base_url}/read/{manga_id}/en/chapter-{data_id}"

                if not chapter_url.startswith('http'):
                    chapter_url = urljoin(self.base_url, chapter_url)

                # Get chapter number from text or data attribute
                chapter_num = link.get('data-number') or item.get('data-number')
                if not chapter_num:
                    chapter_text = link.get_text(strip=True)
                    chapter_num = self._extract_chapter_num(chapter_text)

                # Get title
                title_elem = item.select_one('.name, .title, span')
                title = title_elem.get_text(strip=True) if title_elem else None

                # Get date
                date_elem = item.select_one('.date, .time, time')
                date = date_elem.get_text(strip=True) if date_elem else None

                # Extract chapter ID from URL
                chapter_id = chapter_url

                results.append(ChapterResult(
                    id=chapter_id,
                    chapter=str(chapter_num),
                    title=title,
                    language="en",
                    published=date,
                    url=chapter_url,
                    source=self.id
                ))
            except Exception as e:

                self._log(f"Failed to parse item: {e}")

                continue

        # Sort by chapter number
        def sort_key(ch):
            try:
                return float(ch.chapter) if ch.chapter else 0
            except (ValueError, TypeError):
                return 0

        results.sort(key=sort_key)

        self._log(f"✅ Found {len(results)} chapters")
        return results

    def get_pages(self, chapter_id: str) -> List[PageResult]:
        """Get page images for a chapter."""
        if not HAS_BS4:
            return []

        # chapter_id is the full URL
        url = chapter_id if chapter_id.startswith('http') else f"{self.base_url}{chapter_id}"

        html = self._request_html(url)
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')

        # Try to get images from data attribute or script
        pages = []

        # Method 1: Direct images
        images = soup.select('.read-container img, #readerarea img, .page-img img, .reading-content img')
        for i, img in enumerate(images):
            src = img.get('src') or img.get('data-src') or img.get('data-original')
            if src and 'placeholder' not in src.lower() and 'loading' not in src.lower():
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

        # Method 2: Check for AJAX/JSON data in script
        if not pages:
            scripts = soup.find_all('script')
            for script in scripts:
                text = script.string or ""
                # Look for image arrays
                match = re.search(r'images\s*[=:]\s*(\[.+?\])', text, re.DOTALL)
                if match:
                    try:
                        image_data = json.loads(match.group(1))
                        for i, img_url in enumerate(image_data):
                            if isinstance(img_url, str):
                                pages.append(PageResult(
                                    url=img_url,
                                    index=i,
                                    headers={
                                        "User-Agent": self.USER_AGENT,
                                        "Referer": url
                                    },
                                    referer=url
                                ))
                    except (json.JSONDecodeError, TypeError):
                        pass

        return pages
