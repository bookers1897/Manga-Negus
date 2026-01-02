"""
================================================================================
MangaNegus v2.2 - MangaSee Connector
================================================================================
MangaSee123 / Manga4Life connector.

These are mirror sites with identical structure. They embed manga data
as JavaScript variables in the page, which we extract and parse.

SCRAPING PATTERN:
  Unlike MangaDex/ComicK which have APIs, MangaSee requires scraping.
  We use BeautifulSoup for HTML parsing and regex for JS extraction.

NOTE:
  This site has Cloudflare but is usually passable without solving captchas.
================================================================================
"""

import re
import json
from typing import List, Optional, Dict, Any

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

from .base import (
    BaseConnector, MangaResult, ChapterResult, PageResult, SourceStatus, source_log
)


class MangaSeeConnector(BaseConnector):
    """MangaSee / Manga4Life scraper connector."""
    
    # =========================================================================
    # CONFIGURATION
    # =========================================================================
    
    id = "mangasee"
    name = "MangaSee"
    base_url = "https://manga4life.com"
    icon = "📗"
    
    # URL Detection patterns
    url_patterns = [
        r'https?://(?:www\.)?mangasee123\.com/manga/([A-Za-z0-9-]+)',  # e.g., /manga/Naruto
        r'https?://(?:www\.)?manga4life\.com/manga/([A-Za-z0-9-]+)',   # Alternative domain
    ]
    
    # Conservative - it's a scraping target
    rate_limit = 1.5
    rate_limit_burst = 3
    request_timeout = 20
    
    supports_latest = True
    supports_popular = True
    requires_cloudflare = True  # Has CF but usually passes
    
    languages = ["en"]
    
    USER_AGENT = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
    )
    
    # =========================================================================
    # REQUEST HELPERS
    # =========================================================================
    
    def _headers(self) -> Dict[str, str]:
        """Get browser-like headers for scraping."""
        return {
            "User-Agent": self.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": self.base_url
        }
    
    def _request_html(self, url: str) -> Optional[str]:
        """Fetch HTML from URL with rate limiting."""
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
                # Check for Cloudflare challenge
                if "cf-browser-verification" in response.text:
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
    
    def _log(self, msg: str) -> None:
        """Log message using the central source_log."""
        source_log(f"[{self.id}] {msg}")
    
    # =========================================================================
    # PARSING HELPERS
    # =========================================================================
    
    def _extract_directory(self, html: str) -> List[Dict]:
        """
        Extract manga directory from embedded JavaScript.
        
        MangaSee embeds the full manga list as: vm.Directory = [...];
        We extract this JSON array with regex.
        """
        match = re.search(r'vm\.Directory\s*=\s*(\[.*?\]);', html, re.DOTALL)
        if not match:
            return []
        
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return []
    
    def _extract_chapters(self, html: str) -> List[Dict]:
        """Extract chapter list from embedded JavaScript."""
        match = re.search(r'vm\.Chapters\s*=\s*(\[.*?\]);', html, re.DOTALL)
        if not match:
            return []
        
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return []
    
    def _decode_chapter_num(self, encoded: str) -> str:
        """
        Decode MangaSee's chapter number format.
        
        Format: XXXXYZ where:
          XXXX = chapter number
          Y = decimal (5 = .5)
          Z = version
        
        Example: "100105" = Chapter 1.5
        """
        if not encoded or len(encoded) < 4:
            return encoded
        
        try:
            # Remove first digit (always 1)
            encoded = encoded[1:]
            
            # Get chapter number (first N-1 digits)
            chapter_num = int(encoded[:-1].lstrip("0") or "0")
            
            # Get decimal (last digit)
            decimal = int(encoded[-1])
            
            if decimal > 0:
                return f"{chapter_num}.{decimal}"
            return str(chapter_num)
        except Exception as e:
            self._log(f"Failed to decode chapter number '{encoded}': {e}")
            return encoded
    
    def _build_cover(self, slug: str) -> str:
        """Build cover URL from manga slug."""
        return f"https://temp.compsci88.com/cover/{slug}.jpg"
    
    # =========================================================================
    # PUBLIC API METHODS
    # =========================================================================
    
    def search(self, query: str, page: int = 1) -> List[MangaResult]:
        """
        Search MangaSee for manga.
        
        MangaSee has no search API - we fetch the full directory
        and filter client-side. This is cached after first fetch.
        """
        if not HAS_BS4:
            self._log("⚠️ BeautifulSoup not installed")
            return []
        
        self._log(f"🔍 Searching MangaSee: {query}")
        
        html = self._request_html(f"{self.base_url}/search/")
        if not html:
            return []
        
        directory = self._extract_directory(html)
        if not directory:
            return []
        
        # Filter by query
        query_lower = query.lower()
        matches = []
        
        for manga in directory:
            title = manga.get("s", "")
            alt_names = manga.get("al", [])
            
            if query_lower in title.lower():
                matches.append(manga)
            elif any(query_lower in alt.lower() for alt in alt_names):
                matches.append(manga)
        
        # Paginate
        per_page = 15
        start = (page - 1) * per_page
        end = start + per_page
        
        results = []
        for manga in matches[start:end]:
            slug = manga.get("i", "")
            results.append(MangaResult(
                id=slug,
                title=manga.get("s", slug.replace("-", " ")),
                source=self.id,
                cover_url=self._build_cover(slug),
                author=manga.get("a", [""])[0] if manga.get("a") else None,
                status="ongoing" if manga.get("ss") == "Ongoing" else "completed",
                url=f"{self.base_url}/manga/{slug}",
                genres=manga.get("g", []),
                alt_titles=manga.get("al", [])
            ))
        
        self._log(f"✅ Found {len(results)} results")
        return results
    
    def get_popular(self, page: int = 1) -> List[MangaResult]:
        """Get popular manga by views."""
        html = self._request_html(f"{self.base_url}/search/")
        if not html:
            return []
        
        directory = self._extract_directory(html)
        if not directory:
            return []
        
        # Sort by views
        sorted_manga = sorted(
            directory,
            key=lambda x: int(str(x.get("v", "0")).replace(",", "")),
            reverse=True
        )
        
        per_page = 15
        start = (page - 1) * per_page
        end = start + per_page
        
        results = []
        for manga in sorted_manga[start:end]:
            slug = manga.get("i", "")
            results.append(MangaResult(
                id=slug,
                title=manga.get("s", slug),
                source=self.id,
                cover_url=self._build_cover(slug),
                url=f"{self.base_url}/manga/{slug}"
            ))
        
        return results
    
    def get_latest(self, page: int = 1) -> List[MangaResult]:
        """Get recently updated manga."""
        html = self._request_html(f"{self.base_url}/search/")
        if not html:
            return []
        
        directory = self._extract_directory(html)
        if not directory:
            return []
        
        # Sort by last updated
        sorted_manga = sorted(
            directory,
            key=lambda x: x.get("lt", ""),
            reverse=True
        )
        
        per_page = 15
        start = (page - 1) * per_page
        end = start + per_page
        
        results = []
        for manga in sorted_manga[start:end]:
            slug = manga.get("i", "")
            results.append(MangaResult(
                id=slug,
                title=manga.get("s", slug),
                source=self.id,
                cover_url=self._build_cover(slug),
                url=f"{self.base_url}/manga/{slug}"
            ))
        
        return results
    
    def get_chapters(
        self,
        manga_id: str,
        language: str = "en"
    ) -> List[ChapterResult]:
        """Get chapter list for a manga."""
        self._log(f"📖 Fetching chapters from MangaSee...")
        
        html = self._request_html(f"{self.base_url}/manga/{manga_id}")
        if not html:
            return []
        
        chapters_data = self._extract_chapters(html)
        if not chapters_data:
            self._log("❌ Could not find chapter data")
            return []
        
        results = []
        for ch in chapters_data:
            chapter_num = self._decode_chapter_num(ch.get("Chapter", "0"))
            
            results.append(ChapterResult(
                id=f"{manga_id}-{chapter_num}",
                chapter=chapter_num,
                title=ch.get("ChapterName"),
                language="en",
                published=ch.get("Date"),
                url=f"{self.base_url}/read-online/{manga_id}-chapter-{chapter_num}.html",
                source=self.id
            ))
        
        # Sort by chapter number
        results.sort(key=lambda x: float(x.chapter) if x.chapter else 0)
        
        self._log(f"✅ Found {len(results)} chapters")
        return results
    
    def get_pages(self, chapter_id: str) -> List[PageResult]:
        """Get page images for a chapter."""
        # Parse chapter_id: "manga-slug-chapter-num"
        parts = chapter_id.rsplit("-", 1)
        if len(parts) != 2:
            return []
        
        manga_id, chapter_num = parts
        chapter_url_num = chapter_num.replace(".", "-")
        
        url = f"{self.base_url}/read-online/{manga_id}-chapter-{chapter_url_num}.html"
        html = self._request_html(url)
        if not html:
            return []
        
        # Extract current chapter data
        match = re.search(r'vm\.CurChapter\s*=\s*({.*?});', html, re.DOTALL)
        if not match:
            return []
        
        try:
            cur_chapter = json.loads(match.group(1))
        except json.JSONDecodeError:
            return []
        
        page_count = int(cur_chapter.get("Page", "0"))
        directory = cur_chapter.get("Directory", "")
        chapter_encoded = cur_chapter.get("Chapter", "0")
        
        # Decode chapter for URL
        ch_for_url = self._decode_chapter_num(chapter_encoded)
        ch_padded = ch_for_url.zfill(4)
        
        pages = []
        for i in range(1, page_count + 1):
            if directory:
                img_url = f"https://official.lowee.us/manga/{manga_id}/{directory}/{ch_padded}-{i:03d}.png"
            else:
                img_url = f"https://official.lowee.us/manga/{manga_id}/{ch_padded}-{i:03d}.png"
            
            pages.append(PageResult(
                url=img_url,
                index=i - 1,
                headers={
                    "User-Agent": self.USER_AGENT,
                    "Referer": url
                },
                referer=url
            ))
        
        return pages
