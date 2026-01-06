"""
================================================================================
MangaNegus v3.1 - MangaFire V2 Connector (playwright-stealth)
================================================================================
MangaFire connector using playwright-stealth for advanced Cloudflare bypass.

Replaces cloudscraper with a real browser automation solution that bypasses
modern Cloudflare protection (2026).

BREAKTHROUGH: playwright-stealth provides real browser with anti-detection,
solving the 403 errors encountered with curl_cffi and cloudscraper.
================================================================================
"""

import re
import json
import threading
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin, quote

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

try:
    from playwright.sync_api import sync_playwright, Page, Browser
    from playwright_stealth import Stealth
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

from .base import (
    BaseConnector, MangaResult, ChapterResult, PageResult, SourceStatus, source_log
)


class MangaFireV2Connector(BaseConnector):
    """
    MangaFire scraper with playwright-stealth for Cloudflare bypass.

    Uses real browser automation with stealth mode to bypass Cloudflare's
    advanced bot detection that blocks curl_cffi and cloudscraper.
    """

    id = "mangafire-v2"
    name = "MangaFire V2"
    base_url = "https://mangafire.to"
    icon = "🔥"

    # URL Detection patterns
    url_patterns = [
        r'https?://(?:www\.)?mangafire\.to/manga/([a-z0-9.-]+)',
        r'https?://(?:www\.)?mangafire\.to/read/([a-z0-9.-]+)',
    ]

    rate_limit = 2.0
    rate_limit_burst = 4
    request_timeout = 30

    supports_latest = True
    supports_popular = True
    requires_cloudflare = False  # We bypass it!

    languages = ["en"]

    def __init__(self):
        """Initialize MangaFire V2 with playwright."""
        super().__init__()

        # THREAD SAFETY: Playwright is NOT thread-safe, use lock
        self._playwright_lock = threading.Lock()

        if not HAS_PLAYWRIGHT:
            source_log(f"[{self.id}] playwright not installed! Run: pip install playwright playwright-stealth")
            self._playwright = None
            self._browser = None
            self._page = None
            return

        if not HAS_BS4:
            source_log(f"[{self.id}] BeautifulSoup not installed!")
            self._playwright = None
            self._browser = None
            self._page = None
            return

        try:
            # Initialize playwright
            self._playwright = sync_playwright().start()

            # Launch browser (headless for production)
            self._browser = self._playwright.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox'
                ]
            )

            # Create page with stealth mode
            self._page = self._browser.new_page(
                viewport={'width': 1920, 'height': 1080},
                user_agent=(
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
            )

            # Apply stealth mode to hide automation
            stealth_config = Stealth()
            stealth_config.apply_stealth_sync(self._page)

            source_log(f"[{self.id}] Initialized with playwright-stealth (thread-safe)")

        except Exception as e:
            source_log(f"[{self.id}] Init error: {e}")
            self._playwright = None
            self._browser = None
            self._page = None

    def __del__(self):
        """Cleanup playwright resources (thread-safe)."""
        try:
            # Acquire lock for cleanup to prevent concurrent access
            if hasattr(self, '_playwright_lock'):
                with self._playwright_lock:
                    self._cleanup()
            else:
                self._cleanup()
        except:
            pass

    def _cleanup(self):
        """Internal cleanup helper."""
        try:
            if hasattr(self, '_page') and self._page:
                self._page.close()
                self._page = None
        except:
            pass

        try:
            if hasattr(self, '_browser') and self._browser:
                self._browser.close()
                self._browser = None
        except:
            pass

        try:
            if hasattr(self, '_playwright') and self._playwright:
                self._playwright.stop()
                self._playwright = None
        except:
            pass

    def _get_html(self, url: str, wait_selector: str = None) -> Optional[str]:
        """
        Get HTML content with playwright (thread-safe).

        Args:
            url: URL to fetch
            wait_selector: CSS selector to wait for (optional)

        Returns:
            HTML content or None on failure
        """
        if not self._page:
            return None

        self._wait_for_rate_limit()

        # THREAD SAFETY: Lock Playwright access for concurrent requests
        with self._playwright_lock:
            try:
                # Navigate to URL with load strategy
                response = self._page.goto(url, wait_until='domcontentloaded', timeout=45000)

                if not response or response.status != 200:
                    self._handle_error(f"HTTP {response.status if response else 'no response'}")
                    return None

                # Wait for specific selector if provided
                if wait_selector:
                    try:
                        self._page.wait_for_selector(wait_selector, timeout=15000)
                    except:
                        # Selector not found, but page loaded - might still have content
                        pass
                else:
                    # Default: wait for dynamic content to load
                    self._page.wait_for_timeout(3000)

                # Get page content
                html = self._page.content()

                self._handle_success()
                return html

            except Exception as e:
                self._handle_error(str(e))
                source_log(f"[{self.id}] Request error: {e}")
                return None

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def search(self, query: str, page: int = 1) -> List[MangaResult]:
        """Search MangaFire for manga."""
        if not HAS_BS4 or not self._page:
            return []

        source_log(f"[{self.id}] Searching: {query}")

        # MangaFire search URL
        search_url = f"{self.base_url}/filter?keyword={quote(query)}&page={page}"

        html = self._get_html(search_url, wait_selector='.unit')
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')
        results = []

        # Parse manga cards
        for unit in soup.select('.unit'):
            try:
                # Title and URL
                link = unit.select_one('a.poster')
                if not link:
                    continue

                href = link.get('href', '')
                if not href.startswith('http'):
                    href = urljoin(self.base_url, href)

                # Extract manga ID from URL
                match = re.search(r'/manga/([a-z0-9.-]+)', href)
                manga_id = match.group(1) if match else href.split('/')[-1]

                # Title
                title_elem = unit.select_one('.info .name')
                title = title_elem.text.strip() if title_elem else manga_id.replace('-', ' ').title()

                # Cover image
                img = link.select_one('img')
                cover = img.get('src') or img.get('data-src') if img else None

                results.append(MangaResult(
                    id=manga_id,
                    title=title,
                    source=self.id,
                    cover_url=cover,
                    url=href
                ))

            except Exception as e:
                source_log(f"[{self.id}] Failed to parse item: {e}")
                continue

        source_log(f"[{self.id}] Found {len(results)} results")
        return results

    def get_popular(self, page: int = 1) -> List[MangaResult]:
        """Get popular manga from MangaFire."""
        if not HAS_BS4 or not self._page:
            return []

        url = f"{self.base_url}/filter?sort=most_views&page={page}"

        html = self._get_html(url, wait_selector='.unit')
        if not html:
            return []

        # Use same parsing as search
        soup = BeautifulSoup(html, 'html.parser')
        results = []

        for unit in soup.select('.unit'):
            try:
                link = unit.select_one('a.poster')
                if not link:
                    continue

                href = link.get('href', '')
                if not href.startswith('http'):
                    href = urljoin(self.base_url, href)

                match = re.search(r'/manga/([a-z0-9.-]+)', href)
                manga_id = match.group(1) if match else href.split('/')[-1]

                title_elem = unit.select_one('.info .name')
                title = title_elem.text.strip() if title_elem else manga_id.replace('-', ' ').title()

                img = link.select_one('img')
                cover = img.get('src') or img.get('data-src') if img else None

                results.append(MangaResult(
                    id=manga_id,
                    title=title,
                    source=self.id,
                    cover_url=cover,
                    url=href
                ))

            except Exception as e:
                continue

        return results

    def get_latest(self, page: int = 1) -> List[MangaResult]:
        """Get latest manga updates from MangaFire."""
        if not HAS_BS4 or not self._page:
            return []

        url = f"{self.base_url}/filter?sort=recently_updated&page={page}"

        html = self._get_html(url, wait_selector='.unit')
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')
        results = []

        for unit in soup.select('.unit'):
            try:
                link = unit.select_one('a.poster')
                if not link:
                    continue

                href = link.get('href', '')
                if not href.startswith('http'):
                    href = urljoin(self.base_url, href)

                match = re.search(r'/manga/([a-z0-9.-]+)', href)
                manga_id = match.group(1) if match else href.split('/')[-1]

                title_elem = unit.select_one('.info .name')
                title = title_elem.text.strip() if title_elem else manga_id.replace('-', ' ').title()

                img = link.select_one('img')
                cover = img.get('src') or img.get('data-src') if img else None

                results.append(MangaResult(
                    id=manga_id,
                    title=title,
                    source=self.id,
                    cover_url=cover,
                    url=href
                ))

            except Exception as e:
                continue

        return results

    def get_chapters(self, manga_id: str, language: str = "en") -> List[ChapterResult]:
        """Get chapters for a manga."""
        if not HAS_BS4 or not self._page:
            return []

        source_log(f"[{self.id}] Getting chapters for: {manga_id}")

        url = f"{self.base_url}/manga/{manga_id}"

        html = self._get_html(url, wait_selector='.chapter-item')
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')
        results = []

        for item in soup.select('.chapter-item'):
            try:
                link = item.select_one('a')
                if not link:
                    continue

                href = link.get('href', '')
                if not href.startswith('http'):
                    href = urljoin(self.base_url, href)

                # Extract chapter number from URL or text
                chapter_text = link.text.strip()
                match = re.search(r'chapter[- ]?([\d.]+)', chapter_text, re.I)
                chapter_num = match.group(1) if match else "0"

                results.append(ChapterResult(
                    id=href,  # Use full URL as ID
                    chapter=chapter_num,
                    title=chapter_text,
                    language=language,
                    url=href,
                    source=self.id
                ))

            except Exception as e:
                source_log(f"[{self.id}] Failed to parse chapter: {e}")
                continue

        # Sort by chapter number
        results.sort(key=lambda x: float(x.chapter) if x.chapter.replace('.', '', 1).isdigit() else 0)

        source_log(f"[{self.id}] Found {len(results)} chapters")
        return results

    def get_pages(self, chapter_id: str) -> List[PageResult]:
        """Get page images for a chapter."""
        if not self._page:
            return []

        source_log(f"[{self.id}] Getting pages for chapter")

        html = self._get_html(chapter_id, wait_selector='.img-page')
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')
        pages = []

        for i, img in enumerate(soup.select('.img-page img')):
            src = img.get('src') or img.get('data-src')
            if src:
                if not src.startswith('http'):
                    src = urljoin(self.base_url, src)

                pages.append(PageResult(
                    url=src,
                    index=i,
                    referer=chapter_id
                ))

        source_log(f"[{self.id}] Found {len(pages)} pages")
        return pages
