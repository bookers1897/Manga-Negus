"""AsuraScans Connector - Popular scanlation site"""
import re
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin, quote
try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
from .base import BaseConnector, MangaResult, ChapterResult, PageResult, source_log

class AsuraScansConnector(BaseConnector):
    id = "asurascans"
    name = "AsuraScans"
    base_url = "https://asurascans.com"
    icon = "👹"
    
    # URL Detection patterns
    url_patterns = [
        r'https?://(?:www\.)?asurascans\.com/series/([a-z0-9_-]+)',
        r'https?://(?:www\.)?(?:asura|asuratoon)\.(?:gg|com)/series/([a-z0-9_-]+)',
    ]
    rate_limit = 2.0
    rate_limit_burst = 4
    request_timeout = 20
    supports_latest = True
    supports_popular = True
    requires_cloudflare = True
    languages = ["en"]
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

    def _headers(self) -> Dict[str, str]:
        return {"User-Agent": self.USER_AGENT, "Referer": self.base_url}

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

    def _extract_cover(self, img) -> Optional[str]:
        if not img:
            return None
        srcset = img.get('srcset') or img.get('data-srcset') or ''
        cover = self._pick_srcset_url(srcset)
        if not cover:
            cover = img.get('data-src') or img.get('data-lazy-src') or img.get('data-original') or img.get('src')
        return self._normalize_cover(cover)

    def _log(self, msg: str) -> None:
        """Log message using the central source_log."""
        source_log(f"[{self.id}] {msg}")

    def search(self, query: str, page: int = 1) -> List[MangaResult]:
        if not HAS_BS4: return []
        self._log(f"🔍 Searching AsuraScans: {query}")
        try:
            html = self.fetch_html_raw(f"{self.base_url}/?s={quote(query)}")
        except Exception as e:
            self._log(f"Search failed: {e}")
            return []
            
        soup = BeautifulSoup(html, 'html.parser')
        results = []
        for item in soup.select('.bsx, .listupd .bs')[:20]:
            try:
                link = item.select_one('a')
                if not link: continue
                url = urljoin(self.base_url, link.get('href', ''))
                title = link.get('title', '') or item.select_one('.tt, .title').get_text(strip=True)
                manga_id = url.rstrip('/').split('/')[-1]
                img = item.select_one('img')
                cover = self._extract_cover(img)
                results.append(MangaResult(id=manga_id, title=title, source=self.id, cover_url=cover, url=url))
            except Exception as e:
                self._log(f"Failed to parse item: {e}")
                continue
        self._log(f"✅ Found {len(results)} results")
        return results

    def get_popular(self, page: int = 1) -> List[MangaResult]:
        if not HAS_BS4: return []
        try:
            html = self.fetch_html_raw(f"{self.base_url}/manga/?page={page}&order=popular")
        except Exception: return []
        
        soup = BeautifulSoup(html, 'html.parser')
        results = []
        for item in soup.select('.bsx, .listupd .bs')[:20]:
            try:
                link = item.select_one('a')
                if not link: continue
                url = urljoin(self.base_url, link.get('href', ''))
                title = link.get('title', '') or item.select_one('.tt, .title').get_text(strip=True)
                manga_id = url.rstrip('/').split('/')[-1]
                img = item.select_one('img')
                cover = self._extract_cover(img)
                results.append(MangaResult(id=manga_id, title=title, source=self.id, cover_url=cover, url=url))
            except Exception as e:
                self._log(f"Failed to parse item: {e}")
                continue
        return results

    def get_latest(self, page: int = 1) -> List[MangaResult]:
        return self.get_popular(page)

    def get_chapters(self, manga_id: str, language: str = "en") -> List[ChapterResult]:
        if not HAS_BS4: return []
        self._log(f"📖 Fetching chapters from AsuraScans...")
        url = f"{self.base_url}/series/{manga_id}" if not manga_id.startswith('http') else manga_id
        
        try:
            html = self.fetch_html_raw(url)
        except Exception: return []
        
        soup = BeautifulSoup(html, 'html.parser')
        results = []
        for item in soup.select('#chapterlist li, .eplister li'):
            try:
                link = item.select_one('a')
                if not link: continue
                ch_url = urljoin(self.base_url, link.get('href', ''))
                ch_text = link.get_text(strip=True)
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
        
        try:
            html = self.fetch_html_raw(chapter_id)
        except Exception: return []
        
        soup = BeautifulSoup(html, 'html.parser')
        pages = []
        
        # Primary strategy: specific selector
        for i, img in enumerate(soup.select('#readerarea img, .rdminimal img')):
            src = img.get('src', '') or img.get('data-src', '')
            if src:
                src = urljoin(self.base_url, src)
                pages.append(PageResult(url=src, index=i, headers=self._headers(), referer=chapter_id))
        
        # Fallback strategy: Regex "Hard Scrap" if selectors failed
        if not pages:
            self._log("⚠️ Selectors failed, attempting hard scrap fallback...")
            raw_urls = self.extract_images_raw(html)
            for i, url in enumerate(raw_urls):
                pages.append(PageResult(url=url, index=i, headers=self._headers(), referer=chapter_id))
            
        return pages
