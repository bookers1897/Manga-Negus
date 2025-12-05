"""
================================================================================
MangaNegus v2.3 - WeebCentral Connector (Selenium-powered)
================================================================================
WeebCentral manga source with full Selenium support for JavaScript rendering.

Features:
  - Large manga catalog
  - Good quality scans
  - Selenium-based page scraping for JS-heavy pages
  - Automatic chapter detection
================================================================================
"""

import re
import time
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin, urlparse

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

from .base import (
    BaseConnector, MangaResult, ChapterResult, PageResult, SourceStatus
)
from .webdriver import get_webdriver_manager, is_selenium_available


class WeebCentralConnector(BaseConnector):
    """
    WeebCentral connector using Selenium for JavaScript-heavy pages.
    """

    # =========================================================================
    # CONFIGURATION
    # =========================================================================

    id = "weebcentral"
    name = "WeebCentral"
    base_url = "https://weebcentral.com"
    icon = "🌐"

    rate_limit = 1.5          # Slower due to Selenium overhead
    rate_limit_burst = 3
    request_timeout = 30

    supports_latest = True
    supports_popular = True
    requires_cloudflare = True  # Uses Selenium

    languages = ["en"]

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self):
        super().__init__()
        self._webdriver = None
        if is_selenium_available():
            self._webdriver = get_webdriver_manager()
            self._log("✅ WeebCentral Selenium driver initialized")
        else:
            self._log("⚠️ Selenium not available for WeebCentral")

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

    def _fetch_page(self, url: str, use_selenium: bool = True) -> Optional[str]:
        """
        Fetch a page using Selenium (required for Cloudflare bypass).
        WeebCentral requires Selenium due to heavy Cloudflare protection.
        """
        self._wait_for_rate_limit()

        # Always prefer Selenium for WeebCentral
        if self._webdriver:
            html = self._webdriver.fetch_page(url, delay=2.0)
            if html:
                self._handle_success()
                return html
            self._handle_error("Selenium fetch failed")
            return None

        # Fallback to requests (unlikely to work due to Cloudflare)
        if not self.session:
            return None

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
                self._log("⚠️ WeebCentral blocked - Selenium required")
                return None
            else:
                self._handle_error(f"HTTP {response.status_code}")
                return None

        except Exception as e:
            self._handle_error(str(e))
            return None

    def _log(self, msg: str) -> None:
        """Log message."""
        from sources.base import source_log
        source_log(msg)

    # =========================================================================
    # PARSING HELPERS
    # =========================================================================

    def _extract_manga_id(self, url: str) -> str:
        """Extract manga ID from URL."""
        # WeebCentral URLs: /series/manga-name or /manga/manga-name
        parsed = urlparse(url)
        path_parts = parsed.path.strip('/').split('/')
        if len(path_parts) >= 2:
            return path_parts[1]
        return path_parts[0] if path_parts else ""

    def _extract_chapter_num(self, text: str) -> str:
        """Extract chapter number from text."""
        match = re.search(r'[Cc]h(?:apter)?\.?\s*(\d+(?:\.\d+)?)', text)
        if match:
            return match.group(1)
        # Try just finding numbers
        match = re.search(r'(\d+(?:\.\d+)?)', text)
        return match.group(1) if match else "0"

    # =========================================================================
    # PUBLIC API METHODS
    # =========================================================================

    def search(self, query: str, page: int = 1) -> List[MangaResult]:
        """
        Search WeebCentral for manga using Selenium.

        WeebCentral search URL format: /search/story?query=<query>&page=<page>
        """
        if not HAS_BS4:
            self._log("⚠️ BeautifulSoup not installed")
            return []

        if not self._webdriver:
            self._log("⚠️ Selenium required for WeebCentral search")
            return []

        self._log(f"🔍 Searching WeebCentral: {query}")

        # WeebCentral search URL - use proper format
        from urllib.parse import quote
        encoded_query = quote(query)
        search_url = f"{self.base_url}/search/story?query={encoded_query}&page={page}"

        html = self._fetch_page(search_url)
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')

        # WeebCentral uses article elements or div containers for search results
        items = soup.select('article, div.search-result, a[href*="/series/"]')
        results = []

        for item in items[:20]:
            try:
                # Get link
                if item.name == 'a':
                    link = item
                else:
                    link = item.select_one('a[href*="/series/"]')

                if not link:
                    continue

                manga_url = link.get('href', '')
                if not manga_url.startswith('http'):
                    manga_url = urljoin(self.base_url, manga_url)

                # Skip if not a series link
                if '/series/' not in manga_url:
                    continue

                manga_id = self._extract_manga_id(manga_url)
                if not manga_id:
                    continue

                # Get title - WeebCentral uses various containers
                title_elem = item.select_one('h1, h2, h3, .title, .name, span.title')
                title = title_elem.get_text(strip=True) if title_elem else manga_id.replace('-', ' ').title()

                # Get cover
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
            except Exception:
                continue

        self._log(f"✅ Found {len(results)} results")
        return results

    def get_popular(self, page: int = 1) -> List[MangaResult]:
        """Get popular manga."""
        if not HAS_BS4:
            return []

        url = f"{self.base_url}/popular?page={page}"
        html = self._fetch_page(url)
        if not html:
            # Try alternative URLs
            url = f"{self.base_url}/manga?sort=popular&page={page}"
            html = self._fetch_page(url)

        if not html:
            return []

        return self._parse_manga_list(html)

    def get_latest(self, page: int = 1) -> List[MangaResult]:
        """Get recently updated manga."""
        if not HAS_BS4:
            return []

        url = f"{self.base_url}/latest?page={page}"
        html = self._fetch_page(url)
        if not html:
            url = f"{self.base_url}/manga?sort=latest&page={page}"
            html = self._fetch_page(url)

        if not html:
            return []

        return self._parse_manga_list(html)

    def _parse_manga_list(self, html: str) -> List[MangaResult]:
        """Parse manga list from HTML."""
        soup = BeautifulSoup(html, 'html.parser')

        # Try various selectors
        items = soup.select('article, .manga-item, .series-item, [class*="manga"], [class*="series"]')

        results = []
        for item in items[:20]:
            try:
                link = item.select_one('a[href*="/series/"], a[href*="/manga/"]')
                if not link:
                    link = item if item.name == 'a' else None

                if not link:
                    continue

                manga_url = link.get('href', '')
                if not manga_url.startswith('http'):
                    manga_url = urljoin(self.base_url, manga_url)

                manga_id = self._extract_manga_id(manga_url)
                if not manga_id:
                    continue

                title_elem = item.select_one('h2, h3, .title, .name')
                title = title_elem.get_text(strip=True) if title_elem else manga_id.replace('-', ' ').title()

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
            except Exception:
                continue

        return results

    def get_chapters(
        self,
        manga_id: str,
        language: str = "en"
    ) -> List[ChapterResult]:
        """
        Get chapter list for a manga.

        Based on WeebCentral scraper: uses /full-chapter-list endpoint
        and div[x-data] > a selector for chapters.
        """
        if not HAS_BS4:
            return []

        self._log(f"📖 Fetching chapters from WeebCentral...")

        # Build chapter list URL
        if manga_id.startswith('http'):
            manga_url = manga_id
            manga_id = self._extract_manga_id(manga_id)
        else:
            manga_url = f"{self.base_url}/series/{manga_id}"

        # Parse URL to get proper path for chapter list
        parsed = urlparse(manga_url)
        path_parts = parsed.path.split('/')
        # Build: /series/<id>/full-chapter-list
        chapter_list_url = f"{self.base_url}/{'/'.join(path_parts[:3])}/full-chapter-list"

        self._log(f"📖 Chapter list URL: {chapter_list_url}")
        html = self._fetch_page(chapter_list_url)

        if not html:
            # Fallback to main manga page
            self._log("📖 Falling back to main manga page...")
            html = self._fetch_page(manga_url)

        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')

        # WeebCentral specific selector from original scraper: div[x-data] > a
        chapter_items = soup.select('div[x-data] > a')

        # If no results, try alternative selectors
        if not chapter_items:
            chapter_items = soup.select('a[href*="/chapters/"], a[href*="/chapter/"]')

        results = []
        for item in reversed(chapter_items):  # Reverse to get oldest first
            try:
                if item.name == 'a':
                    link = item
                else:
                    link = item.select_one('a')

                if not link:
                    continue

                chapter_url = link.get('href', '')
                if not chapter_url.startswith('http'):
                    chapter_url = urljoin(self.base_url, chapter_url)

                # Get chapter name from span.flex > span (WeebCentral specific)
                name_elem = link.select_one('span.flex > span')
                if name_elem:
                    chapter_text = name_elem.get_text(strip=True)
                else:
                    chapter_text = link.get_text(strip=True)

                chapter_num = self._extract_chapter_num(chapter_text)

                results.append(ChapterResult(
                    id=chapter_url,
                    chapter=chapter_num,
                    title=chapter_text,
                    language="en",
                    url=chapter_url,
                    source=self.id
                ))
            except Exception:
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
        """Get page images for a chapter using Selenium."""
        self._log(f"📄 Fetching pages with Selenium...")

        # chapter_id is the full URL
        url = chapter_id if chapter_id.startswith('http') else f"{self.base_url}{chapter_id}"

        # Use Selenium for JavaScript-rendered pages
        if self._webdriver:
            images = self._webdriver.get_images_from_page(
                url,
                image_selector="img[src*='/manga/'], img.page-img, .reader-content img",
                wait_timeout=10,
                delay=3.0
            )

            pages = []
            for i, img_url in enumerate(images):
                # Filter out unwanted images
                if any(word in img_url.lower() for word in ['avatar', 'icon', 'logo', 'banner', 'brand']):
                    continue

                pages.append(PageResult(
                    url=img_url,
                    index=i,
                    headers={
                        "User-Agent": self.USER_AGENT,
                        "Referer": url
                    },
                    referer=url
                ))

            self._log(f"✅ Found {len(pages)} pages")
            return pages

        # Fallback to regular requests (less reliable for WeebCentral)
        if HAS_BS4:
            html = self._fetch_page(url)
            if html:
                soup = BeautifulSoup(html, 'html.parser')
                images = soup.select('img[src*="/manga/"], img.page-img, .reader-content img')

                pages = []
                for i, img in enumerate(images):
                    src = img.get('src') or img.get('data-src')
                    if src and 'placeholder' not in src.lower():
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

        return []

    def get_manga_details(self, manga_id: str) -> Optional[MangaResult]:
        """
        Get detailed manga info.

        Based on WeebCentral scraper selectors:
        - Title: section[x-data] > section:nth-of-type(2) h1
        - Cover: img[alt$='cover']
        """
        if not HAS_BS4:
            return None

        if manga_id.startswith('http'):
            url = manga_id
            manga_id = self._extract_manga_id(manga_id)
        else:
            url = f"{self.base_url}/series/{manga_id}"

        html = self._fetch_page(url)
        if not html:
            return None

        soup = BeautifulSoup(html, 'html.parser')

        # Extract title - WeebCentral specific selector
        title_elem = soup.select_one('section[x-data] > section:nth-of-type(2) h1')
        if not title_elem:
            title_elem = soup.select_one('h1, .manga-title, .series-title')
        title = title_elem.get_text(strip=True) if title_elem else manga_id.replace('-', ' ').title()

        # Extract cover - WeebCentral uses img[alt$='cover']
        cover_elem = soup.select_one("img[alt$='cover']")
        if not cover_elem:
            cover_elem = soup.select_one('.cover img, .manga-cover img, img.cover')
        cover = None
        if cover_elem:
            cover = cover_elem.get('src') or cover_elem.get('data-src')
            if cover and not cover.startswith('http'):
                cover = urljoin(self.base_url, cover)

        # Extract description
        desc_elem = soup.select_one('.description, .summary, .synopsis, p.description')
        description = desc_elem.get_text(strip=True) if desc_elem else None

        # Extract author
        author_elem = soup.select_one('.author, [class*="author"], a[href*="/author/"]')
        author = author_elem.get_text(strip=True) if author_elem else None

        # Extract status
        status_elem = soup.select_one('.status, [class*="status"]')
        status = status_elem.get_text(strip=True).lower() if status_elem else None

        # Extract genres
        genres = []
        genre_elems = soup.select('.genre, .tag, a[href*="/genre/"]')
        for g in genre_elems:
            genres.append(g.get_text(strip=True))

        return MangaResult(
            id=manga_id,
            title=title,
            source=self.id,
            cover_url=cover,
            description=description,
            author=author,
            status=status,
            url=url,
            genres=genres
        )
