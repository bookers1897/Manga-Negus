"""
================================================================================
MangaNegus v2.3 - MangaKakalot/Manganato Connector
================================================================================
MangaKakalot family connector (manganato.com, chapmanganato.to, etc.)

These are high-traffic manga aggregators that change domains frequently.
We support multiple mirrors with identical HTML structure.

ANTI-HOTLINK PROTECTION:
  Images require the correct Referer header or they return 403.
  Always send the chapter page URL as referer when downloading images.
================================================================================
"""

import re
from typing import List, Optional, Dict, Any

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

from .base import (
    BaseConnector, MangaResult, ChapterResult, PageResult, SourceStatus
)


class MangaKakalotConnector(BaseConnector):
    """MangaKakalot / Manganato scraper connector."""
    
    # =========================================================================
    # CONFIGURATION
    # =========================================================================
    
    id = "mangakakalot"
    name = "Manganato"
    base_url = "https://mangakakalot.gg"  # Updated to new domain (2025)
    icon = "📙"

    rate_limit = 2.0
    rate_limit_burst = 4
    request_timeout = 20

    supports_latest = True
    supports_popular = True
    requires_cloudflare = False

    languages = ["en"]

    # Mirror domains (try in order if one fails) - Updated for 2025
    MIRRORS = [
        "https://mangakakalot.gg",
        "https://chapmanganato.to",
        "https://manganato.com",
        "https://readmanganato.com"
    ]
    
    USER_AGENT = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
    )
    
    # =========================================================================
    # REQUEST HELPERS
    # =========================================================================
    
    def _headers(self, referer: Optional[str] = None) -> Dict[str, str]:
        """Get request headers with optional referer."""
        headers = {
            "User-Agent": self.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5"
        }
        if referer:
            headers["Referer"] = referer
        return headers
    
    def _request_html(self, url: str) -> Optional[str]:
        """Fetch HTML with rate limiting."""
        if not self.session:
            return None
        
        self._wait_for_rate_limit()
        
        try:
            response = self.session.get(
                url,
                headers=self._headers(self.base_url),
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
        """Log message."""
        from sources.base import source_log
        source_log(msg)
    
    # =========================================================================
    # PARSING HELPERS
    # =========================================================================
    
    def _extract_manga_id(self, url: str) -> str:
        """Extract manga ID from URL."""
        # URLs like: https://manganato.com/manga-xy123456
        match = re.search(r'manga[_-](\w+)', url)
        if match:
            return match.group(0)  # Return full "manga-xyz" 
        return url.rstrip('/').split('/')[-1]
    
    def _extract_chapter_num(self, text: str) -> str:
        """Extract chapter number from chapter title."""
        # Patterns: "Chapter 123", "Ch. 123", "Chapter 123.5"
        match = re.search(r'[Cc]h(?:apter)?\.?\s*(\d+(?:\.\d+)?)', text)
        return match.group(1) if match else "0"
    
    # =========================================================================
    # PUBLIC API METHODS
    # =========================================================================
    
    def search(self, query: str, page: int = 1) -> List[MangaResult]:
        """Search for manga."""
        if not HAS_BS4:
            self._log("⚠️ BeautifulSoup not installed")
            return []
        
        self._log(f"🔍 Searching Manganato: {query}")
        
        # Format query for URL
        query_formatted = query.replace(' ', '_').lower()
        url = f"{self.base_url}/search/story/{query_formatted}?page={page}"
        
        html = self._request_html(url)
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find search results
        container = soup.select_one('.panel-search-story, .panel_story_list')
        if not container:
            return []
        
        items = container.select('.search-story-item, .story_item')
        results = []
        
        for item in items:
            try:
                # Get link
                link = item.select_one('a.item-img, a.story_item, a')
                if not link:
                    continue
                
                manga_url = link.get('href', '')
                manga_id = self._extract_manga_id(manga_url)
                
                # Get cover
                img = item.select_one('img')
                cover = img.get('src', '') if img else None
                
                # Get title
                title_elem = item.select_one('h3 a, .item-title, .story_name a')
                title = title_elem.get_text(strip=True) if title_elem else "Unknown"
                
                # Get author
                author_elem = item.select_one('.item-author, .story_author')
                author = author_elem.get_text(strip=True) if author_elem else None
                
                results.append(MangaResult(
                    id=manga_id,
                    title=title,
                    source=self.id,
                    cover_url=cover,
                    author=author,
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
        
        url = f"{self.base_url}/genre-all?page={page}"
        html = self._request_html(url)
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        items = soup.select('.content-genres-item, .list-truyen-item-wrap')
        
        results = []
        for item in items:
            try:
                link = item.select_one('a.genres-item-img, a')
                if not link:
                    continue
                
                manga_url = link.get('href', '')
                manga_id = self._extract_manga_id(manga_url)
                
                img = item.select_one('img')
                cover = img.get('src', '') if img else None
                
                title_elem = item.select_one('h3 a, .genres-item-name')
                title = title_elem.get_text(strip=True) if title_elem else "Unknown"
                
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
    
    def get_latest(self, page: int = 1) -> List[MangaResult]:
        """Get recently updated manga."""
        if not HAS_BS4:
            return []
        
        url = f"{self.base_url}/genre-all/{page}?type=latest"
        html = self._request_html(url)
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        items = soup.select('.content-genres-item, .list-truyen-item-wrap')
        
        results = []
        for item in items:
            try:
                link = item.select_one('a')
                if not link:
                    continue
                
                manga_url = link.get('href', '')
                manga_id = self._extract_manga_id(manga_url)
                
                img = item.select_one('img')
                cover = img.get('src', '') if img else None
                
                title_elem = item.select_one('h3 a, .genres-item-name')
                title = title_elem.get_text(strip=True) if title_elem else "Unknown"
                
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
        """Get chapter list for a manga."""
        if not HAS_BS4:
            return []
        
        self._log(f"📖 Fetching chapters from Manganato...")
        
        # Build manga URL
        if manga_id.startswith('http'):
            url = manga_id
        elif manga_id.startswith('manga'):
            url = f"{self.base_url}/{manga_id}"
        else:
            url = f"{self.base_url}/manga-{manga_id}"
        
        html = self._request_html(url)
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find chapter list
        chapter_items = soup.select('.row-content-chapter li, .chapter-list .row')
        
        results = []
        for item in chapter_items:
            try:
                link = item.select_one('a')
                if not link:
                    continue
                
                chapter_url = link.get('href', '')
                chapter_title = link.get_text(strip=True)
                chapter_num = self._extract_chapter_num(chapter_title)
                
                # Get date
                date_elem = item.select_one('.chapter-time, span:last-child')
                date = None
                if date_elem:
                    date = date_elem.get('title', date_elem.get_text(strip=True))
                
                results.append(ChapterResult(
                    id=chapter_url,  # Use URL as ID
                    chapter=chapter_num,
                    title=chapter_title,
                    language="en",
                    published=date,
                    url=chapter_url,
                    source=self.id
                ))
            except Exception:
                continue
        
        # Reverse to get ascending order
        results.reverse()
        
        # Sort by chapter number
        results.sort(key=lambda x: float(x.chapter) if x.chapter else 0)
        
        self._log(f"✅ Found {len(results)} chapters")
        return results
    
    def get_pages(self, chapter_id: str) -> List[PageResult]:
        """
        Get page images for a chapter.
        
        IMPORTANT: Must send correct Referer header for images!
        """
        if not HAS_BS4:
            return []
        
        # chapter_id is the full URL
        url = chapter_id
        
        html = self._request_html(url)
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find page images
        images = soup.select(
            '.container-chapter-reader img, '
            '.reading-content img, '
            '.page-chapter img'
        )
        
        pages = []
        for i, img in enumerate(images):
            src = img.get('src', '') or img.get('data-src', '')
            
            # Skip loading placeholder gifs
            if src and not src.endswith('.gif'):
                pages.append(PageResult(
                    url=src,
                    index=i,
                    headers={
                        "User-Agent": self.USER_AGENT,
                        "Referer": url  # CRITICAL: Required for images!
                    },
                    referer=url
                ))
        
        return pages
