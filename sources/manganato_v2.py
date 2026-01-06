"""
================================================================================
MangaNegus v3.0 - MangaNato V2 Connector (curl_cffi)
================================================================================
MangaNato / Manganelo connector using curl_cffi for Cloudflare bypass.

Replaces the Enma library with a direct, high-performance scraper that mimics
a real browser to bypass protections on manganato.com and chapmanganato.com.
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

try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

from .base import (
    BaseConnector, MangaResult, ChapterResult, PageResult, SourceStatus, source_log
)


class MangaNatoV2Connector(BaseConnector):
    """MangaNato scraper with Cloudflare bypass."""
    
    id = "manganato-v2"
    name = "MangaKakalot"  # Updated Jan 2026: domain migration
    base_url = "https://mangakakalot.gg"  # Working domain as of Jan 2026
    icon = "📖"

    # URL Detection patterns (updated for new domain)
    url_patterns = [
        r'https?://(?:www\.)?mangakakalot\.gg/manga-([a-z0-9]+)',
        r'https?://(?:www\.)?mangakakalot\.gg/read-([a-z0-9]+)',
        # Legacy patterns for old domains
        r'https?://(?:www\.)?(?:manganato|manganelo|chapmanganato)\.(?:com|gg|to)/manga-([a-z0-9]+)',
        r'https?://(?:www\.)?(?:manganato|manganelo|chapmanganato)\.(?:com|gg|to)/read-([a-z0-9]+)',
    ]
    
    rate_limit = 1.0
    rate_limit_burst = 5
    request_timeout = 30
    
    supports_latest = True
    supports_popular = True
    requires_cloudflare = False
    
    languages = ["en"]
    
    def __init__(self):
        super().__init__()
        if HAS_CURL_CFFI:
            self._session = curl_requests.Session()
        else:
            self._session = None
            source_log(f"[{self.id}] curl_cffi not installed!")

    def _get(self, url: str) -> Optional[str]:
        """Make GET request with Chrome impersonation."""
        if not self._session:
            return None
            
        self._wait_for_rate_limit()
        
        try:
            response = self._session.get(
                url,
                impersonate="chrome120",
                timeout=self.request_timeout,
                headers={
                    "Referer": "https://mangakakalot.gg/",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9"
                }
            )
            
            if response.status_code == 200:
                self._handle_success()
                return response.text
            elif response.status_code == 403:
                self._handle_cloudflare()
                return None
            else:
                self._handle_error(f"HTTP {response.status_code}")
                return None
                
        except Exception as e:
            self._handle_error(str(e))
            return None

    def get_download_session(self):
        """Use curl_cffi session for downloads."""
        return self._session

    # =========================================================================
    # PUBLIC API
    # =========================================================================
    
    def search(self, query: str, page: int = 1) -> List[MangaResult]:
        if not HAS_BS4: return []
        
        # Format: https://manganato.com/search/story/<query_safe>?page=1
        safe_query = query.replace(" ", "_").replace("'", "").lower()
        # Remove non-alphanumeric except underscore
        safe_query = "".join(c for c in safe_query if c.isalnum() or c == "_")
        
        url = f"{self.base_url}/search/story/{safe_query}?page={page}"
        html = self._get(url)
        if not html: return []
        
        soup = BeautifulSoup(html, 'html.parser')
        results = []

        # MangaKakalot.gg uses .story_item (updated Jan 2026)
        for item in soup.select('.story_item'):
            try:
                # Title and URL from h3.story_name > a
                title_link = item.select_one('h3.story_name a')
                if not title_link:
                    continue

                href = title_link.get('href', '')
                title = title_link.text.strip()
                manga_id = href.split('/')[-1] if href else ""

                # Cover image
                img = item.select_one('img')
                cover = img.get('src') if img else None

                # Author from span containing "Author(s)"
                author = None
                for span in item.select('span'):
                    text = span.text.strip()
                    if 'Author' in text:
                        author = text.replace('Author(s) :', '').strip()
                        break

                results.append(MangaResult(
                    id=manga_id,
                    title=title,
                    source=self.id,
                    cover_url=cover,
                    url=href,
                    author=author
                ))
            except Exception as e:
                source_log(f"[{self.id}] Failed to parse item: {e}")
                continue
            
        return results
    
    def get_popular(self, page: int = 1) -> List[MangaResult]:
        # Homepage has popular section, or use genre-all
        url = f"{self.base_url}/genre-all/{page}?type=topview"
        html = self._get(url)
        if not html: return []
        
        soup = BeautifulSoup(html, 'html.parser')
        results = []
        
        for item in soup.select('.content-genres-item'):
            try:
                link = item.select_one('a.genres-item-img')
                if not link: continue
                
                href = link.get('href')
                manga_id = href.split('/')[-1]
                
                img = link.select_one('img')
                cover = img.get('src')
                title = img.get('alt')
                
                results.append(MangaResult(
                    id=manga_id,
                    title=title,
                    source=self.id,
                    cover_url=cover,
                    url=href
                ))
            except: continue
            
        return results

    def get_latest(self, page: int = 1) -> List[MangaResult]:
        url = f"{self.base_url}/genre-all/{page}"
        html = self._get(url)
        if not html: return []
        
        soup = BeautifulSoup(html, 'html.parser')
        results = []
        
        for item in soup.select('.content-genres-item'):
            try:
                link = item.select_one('a.genres-item-img')
                href = link.get('href')
                manga_id = href.split('/')[-1]
                img = link.select_one('img')
                
                results.append(MangaResult(
                    id=manga_id,
                    title=img.get('alt'),
                    source=self.id,
                    cover_url=img.get('src'),
                    url=href
                ))
            except: continue
            
        return results

    def get_chapters(self, manga_id: str, language: str = "en") -> List[ChapterResult]:
        source_log(f"[{self.id}] Getting chapters for {manga_id}")

        # Updated Jan 2026: use mangakakalot.gg
        # URL format: https://mangakakalot.gg/manga/<id>
        url = f"{self.base_url}/manga/{manga_id}"

        html = self._get(url)
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')
        results = []

        # MangaKakalot.gg uses .chapter-list > .row structure (updated Jan 2026)
        for row in soup.select('.chapter-list .row'):
            try:
                link = row.select_one('a')
                if not link:
                    continue

                href = link.get('href', '')
                title = link.text.strip()

                # Extract chapter number
                match = re.search(r'chapter[-_ ]([\d\.]+)', href)
                num = match.group(1) if match else "0"

                # Published date from span with title attribute
                date_spans = row.select('span[title]')
                date = date_spans[0].get('title') if date_spans else None

                results.append(ChapterResult(
                    id=href,  # Use full URL as ID for easy page fetching
                    chapter=num,
                    title=title,
                    language="en",
                    published=date,
                    url=href,
                    source=self.id
                ))
            except Exception as e:
                source_log(f"[{self.id}] Failed to parse chapter: {e}")
                continue
            
        results.sort(key=lambda x: float(x.chapter) if x.chapter.replace('.', '', 1).isdigit() else 0)
        return results

    def get_pages(self, chapter_id: str) -> List[PageResult]:
        # chapter_id is the full URL
        html = self._get(chapter_id)
        if not html: return []
        
        soup = BeautifulSoup(html, 'html.parser')
        pages = []
        
        container = soup.select_one('.container-chapter-reader')
        if not container: return []
        
        for i, img in enumerate(container.select('img')):
            src = img.get('src')
            if src:
                pages.append(PageResult(
                    url=src,
                    index=i,
                    headers={"Referer": "https://chapmanganato.com/"},
                    referer=chapter_id
                ))
                
        return pages
