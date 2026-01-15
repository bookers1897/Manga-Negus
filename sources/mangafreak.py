"""MangaFreak Connector - Reliable backup source with Cloudflare bypass"""
import re
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin, quote

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

# Try curl_cffi for Cloudflare bypass (recommended)
try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

# Fallback to cloudscraper
try:
    import cloudscraper
    HAS_CLOUDSCRAPER = True
except ImportError:
    HAS_CLOUDSCRAPER = False

from .base import BaseConnector, MangaResult, ChapterResult, PageResult, source_log


class MangaFreakConnector(BaseConnector):
    id = "mangafreak"
    name = "MangaFreak"
    base_url = "https://mangafreak.net"
    icon = "😈"

    # URL Detection patterns
    url_patterns = [
        r'https?://(?:www\.)?mangafreak\.net/manga/([a-z0-9_-]+)',  # e.g., /manga/naruto
        r'https?://(?:www\.)?mangafreak\.net/Manga/([a-z0-9_-]+)',  # e.g., /Manga/Naruto
    ]
    rate_limit = 2.0
    rate_limit_burst = 4
    request_timeout = 20
    supports_latest = True
    supports_popular = True
    requires_cloudflare = True
    languages = ["en"]

    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    def __init__(self):
        super().__init__()
        # Initialize Cloudflare bypass session
        self._cf_session = None
        if HAS_CURL_CFFI:
            self._cf_session = curl_requests.Session()
            self._log("✅ MangaFreak using curl_cffi bypass")
        elif HAS_CLOUDSCRAPER:
            self._cf_session = cloudscraper.create_scraper()
            self._log("✅ MangaFreak using cloudscraper bypass")
        else:
            self._log("⚠️ MangaFreak: No Cloudflare bypass available")

    def _headers(self) -> Dict[str, str]:
        return {
            "User-Agent": self.USER_AGENT,
            "Referer": self.base_url,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

    def _request_html(self, url: str) -> Optional[str]:
        self._wait_for_rate_limit()
        try:
            # Prefer curl_cffi for Cloudflare bypass
            if HAS_CURL_CFFI and self._cf_session:
                r = self._cf_session.get(
                    url,
                    headers=self._headers(),
                    timeout=self.request_timeout,
                    impersonate="chrome120"
                )
            elif self._cf_session:
                r = self._cf_session.get(url, headers=self._headers(), timeout=self.request_timeout)
            elif self.session:
                r = self.session.get(url, headers=self._headers(), timeout=self.request_timeout)
            else:
                return None

            if r.status_code == 200:
                self._handle_success()
                return r.text
            elif r.status_code in [403, 503]:
                self._handle_cloudflare()
            elif r.status_code == 429:
                self._handle_rate_limit(60)
            else:
                self._handle_error(f"HTTP {r.status_code}")
        except Exception as e:
            self._handle_error(str(e))
        return None

    def _log(self, msg: str) -> None:
        """Log message using the central source_log."""
        source_log(f"[{self.id}] {msg}")

    def search(self, query: str, page: int = 1) -> List[MangaResult]:
        if not HAS_BS4: return []
        self._log(f"🔍 Searching MangaFreak: {query}")
        html = self._request_html(f"{self.base_url}/Find/{quote(query)}")
        if not html: return []
        soup = BeautifulSoup(html, 'html.parser')
        results = []
        for item in soup.select('.manga_search_item, .rank_item')[:20]:
            try:
                link = item.select_one('a')
                if not link: continue
                url = urljoin(self.base_url, link.get('href', ''))
                title = link.get('title', '') or link.get_text(strip=True)
                manga_id = url.rstrip('/').split('/')[-1]
                img = item.select_one('img')
                cover = urljoin(self.base_url, img.get('src', '')) if img else None
                results.append(MangaResult(id=manga_id, title=title, source=self.id, cover_url=cover, url=url))
            except Exception as e:
                self._log(f"Failed to parse item: {e}")
                continue
        self._log(f"✅ Found {len(results)} results")
        return results

    def get_popular(self, page: int = 1) -> List[MangaResult]:
        if not HAS_BS4: return []
        html = self._request_html(f"{self.base_url}/Rank/Week")
        if not html: return []
        soup = BeautifulSoup(html, 'html.parser')
        results = []
        for item in soup.select('.rank_item')[:20]:
            try:
                link = item.select_one('a')
                if not link: continue
                url = urljoin(self.base_url, link.get('href', ''))
                title = link.get('title', '') or link.get_text(strip=True)
                manga_id = url.rstrip('/').split('/')[-1]
                img = item.select_one('img')
                cover = urljoin(self.base_url, img.get('src', '')) if img else None
                results.append(MangaResult(id=manga_id, title=title, source=self.id, cover_url=cover, url=url))
            except Exception as e:
                self._log(f"Failed to parse item: {e}")
                continue
        return results

    def get_latest(self, page: int = 1) -> List[MangaResult]:
        return self.get_popular(page)

    def get_chapters(self, manga_id: str, language: str = "en") -> List[ChapterResult]:
        if not HAS_BS4: return []
        self._log(f"📖 Fetching chapters from MangaFreak...")
        url = f"{self.base_url}/Manga/{manga_id}" if not manga_id.startswith('http') else manga_id
        html = self._request_html(url)
        if not html: return []
        soup = BeautifulSoup(html, 'html.parser')
        results = []
        for item in soup.select('.chapter_list a, .manga_series_list a'):
            try:
                ch_url = urljoin(self.base_url, item.get('href', ''))
                ch_text = item.get_text(strip=True)
                match = re.search(r'[Cc]h(?:apter)?\.?\s*(\d+(?:\.\d+)?)', ch_text)
                ch_num = match.group(1) if match else "0"
                results.append(ChapterResult(id=ch_url, chapter=ch_num, title=ch_text, language="en", url=ch_url, source=self.id))
            except Exception as e:
                self._log(f"Failed to parse item: {e}")
                continue
        results.sort(key=lambda x: float(x.chapter) if x.chapter else 0)
        self._log(f"✅ Found {len(results)} chapters")
        return results

    def get_pages(self, chapter_id: str) -> List[PageResult]:
        if not HAS_BS4: return []
        html = self._request_html(chapter_id)
        if not html: return []
        soup = BeautifulSoup(html, 'html.parser')
        pages = []
        for i, img in enumerate(soup.select('.read_img img, #gohere img')):
            src = img.get('src', '') or img.get('data-src', '')
            if src:
                src = urljoin(self.base_url, src)
                pages.append(PageResult(url=src, index=i, headers=self._headers(), referer=chapter_id))
        return pages
