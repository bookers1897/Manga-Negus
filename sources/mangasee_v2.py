"""
================================================================================
MangaNegus v3.0 - MangaSee V2 Connector (curl_cffi)
================================================================================
MangaSee123 / Manga4Life connector using curl_cffi for Cloudflare bypass.

This V2 connector replaces the standard requests library with curl_cffi
to handle TLS fingerprinting and bypass anti-bot protections.
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

try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

from .base import (
    BaseConnector, MangaResult, ChapterResult, PageResult, SourceStatus, source_log
)


class MangaSeeV2Connector(BaseConnector):
    """MangaSee / Manga4Life scraper with Cloudflare bypass."""
    
    id = "mangasee-v2"
    name = "MangaSee V2"
    base_url = "https://manga4life.com"
    icon = "📗"
    
    # URL Detection patterns
    url_patterns = [
        r'https?://(?:www\.)?mangasee123\.com/manga/([A-Za-z0-9-]+)',
        r'https?://(?:www\.)?manga4life\.com/manga/([A-Za-z0-9-]+)',
    ]
    
    rate_limit = 1.0
    rate_limit_burst = 3
    request_timeout = 30
    
    supports_latest = True
    supports_popular = True
    requires_cloudflare = False # Handled internally
    
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
            # Visit homepage first if we don't have cookies
            if not self._session.cookies:
                self._session.get(self.base_url, impersonate="chrome120")

            response = self._session.get(
                url,
                impersonate="chrome120",
                timeout=self.request_timeout
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
    # PARSING HELPERS (Reused from V1)
    # =========================================================================
    
    def _extract_directory(self, html: str) -> List[Dict]:
        match = re.search(r'vm\.Directory\s*=\s*(\[.*?\]);', html, re.DOTALL)
        if not match: return []
        try: return json.loads(match.group(1))
        except json.JSONDecodeError: return []
    
    def _extract_chapters(self, html: str) -> List[Dict]:
        match = re.search(r'vm\.Chapters\s*=\s*(\[.*?\]);', html, re.DOTALL)
        if not match: return []
        try: return json.loads(match.group(1))
        except json.JSONDecodeError: return []
    
    def _decode_chapter_num(self, encoded: str) -> str:
        if not encoded or len(encoded) < 4: return encoded
        try:
            encoded = encoded[1:]
            chapter_num = int(encoded[:-1].lstrip("0") or "0")
            decimal = int(encoded[-1])
            return f"{chapter_num}.{decimal}" if decimal > 0 else str(chapter_num)
        except: return encoded
    
    def _build_cover(self, slug: str) -> str:
        return f"https://temp.compsci88.com/cover/{slug}.jpg"
    
    # =========================================================================
    # PUBLIC API
    # =========================================================================
    
    def search(self, query: str, page: int = 1) -> List[MangaResult]:
        if not HAS_BS4: return []
        
        # MangaSee has no search API, fetch directory
        html = self._get(f"{self.base_url}/search/")
        if not html: return []
        
        directory = self._extract_directory(html)
        if not directory: return []
        
        query_lower = query.lower()
        matches = [m for m in directory if query_lower in m.get("s", "").lower() or 
                  any(query_lower in alt.lower() for alt in m.get("al", []))]
        
        per_page = 20
        start = (page - 1) * per_page
        end = start + per_page
        
        results = []
        for m in matches[start:end]:
            slug = m.get("i", "")
            results.append(MangaResult(
                id=slug,
                title=m.get("s", slug),
                source=self.id,
                cover_url=self._build_cover(slug),
                url=f"{self.base_url}/manga/{slug}",
                status="ongoing" if m.get("ss") == "Ongoing" else "completed"
            ))
        
        return results
    
    def get_popular(self, page: int = 1) -> List[MangaResult]:
        html = self._get(f"{self.base_url}/search/")
        if not html: return []
        
        directory = self._extract_directory(html)
        # Sort by views (v)
        sorted_manga = sorted(directory, key=lambda x: int(str(x.get("v", "0")).replace(",", "")), reverse=True)
        
        per_page = 20
        start = (page - 1) * per_page
        end = start + per_page
        
        results = []
        for m in sorted_manga[start:end]:
            slug = m.get("i", "")
            results.append(MangaResult(
                id=slug,
                title=m.get("s", slug),
                source=self.id,
                cover_url=self._build_cover(slug),
                url=f"{self.base_url}/manga/{slug}"
            ))
        return results

    def get_latest(self, page: int = 1) -> List[MangaResult]:
        html = self._get(f"{self.base_url}/search/")
        if not html: return []
        
        directory = self._extract_directory(html)
        # Sort by last updated (lt)
        sorted_manga = sorted(directory, key=lambda x: int(x.get("lt", "0")), reverse=True)
        
        per_page = 20
        start = (page - 1) * per_page
        end = start + per_page
        
        results = []
        for m in sorted_manga[start:end]:
            slug = m.get("i", "")
            results.append(MangaResult(
                id=slug,
                title=m.get("s", slug),
                source=self.id,
                cover_url=self._build_cover(slug),
                url=f"{self.base_url}/manga/{slug}"
            ))
        return results

    def get_chapters(self, manga_id: str, language: str = "en") -> List[ChapterResult]:
        source_log(f"[{self.id}] Fetching chapters for {manga_id}")
        html = self._get(f"{self.base_url}/manga/{manga_id}")
        if not html: return []
        
        chapters_data = self._extract_chapters(html)
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
            
        results.sort(key=lambda x: float(x.chapter) if x.chapter.replace('.', '', 1).isdigit() else 0)
        return results

    def get_pages(self, chapter_id: str) -> List[PageResult]:
        parts = chapter_id.rsplit("-", 1)
        if len(parts) != 2: return []
        manga_id, chapter_num = parts
        chapter_url_num = chapter_num.replace(".", "-")
        
        url = f"{self.base_url}/read-online/{manga_id}-chapter-{chapter_url_num}.html"
        html = self._get(url)
        if not html: return []
        
        match = re.search(r'vm\.CurChapter\s*=\s*({.*?});', html, re.DOTALL)
        if not match: return []
        
        try:
            cur_chapter = json.loads(match.group(1))
            page_count = int(cur_chapter.get("Page", "0"))
            directory = cur_chapter.get("Directory", "")
            ch_padded = self._decode_chapter_num(cur_chapter.get("Chapter", "0")).zfill(4)
            
            pages = []
            for i in range(1, page_count + 1):
                # Host logic per official implementation
                host = "https://official.lowee.us"
                path = f"/manga/{manga_id}"
                if directory: path += f"/{directory}"
                path += f"/{ch_padded}-{i:03d}.png"
                
                pages.append(PageResult(
                    url=host + path,
                    index=i - 1,
                    headers={"Referer": url},
                    referer=url
                ))
            return pages
        except: return []
