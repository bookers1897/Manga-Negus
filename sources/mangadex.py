"""
================================================================================
MangaNegus v2.2 - MangaDex Connector
================================================================================
MangaDex API v5 connector with PROPER rate limiting.

WHY YOU GOT BANNED:
  - MangaDex allows 5 requests/second at their load balancer
  - Your old code had NO delays between requests
  - When you hit 429, retrying immediately makes it WORSE
  - Continued requests after 429 = temporary IP ban (403)

THIS IMPLEMENTATION:
  - 2 req/sec rate limit (conservative, below their 5/sec limit)
  - Immediate STOP on 429 (no retrying!)
  - Proper User-Agent that identifies your app
  - Exponential backoff with jitter on errors

MANGADEX API RULES:
  - User-Agent MUST identify your app (no browser spoofing)
  - Don't send auth headers when downloading images
  - Use /at-home/server/ for dynamic CDN URLs
  - Report download success/failure (optional but nice)
================================================================================
"""

import time
from typing import List, Optional, Dict, Any
from .base import (
    BaseConnector, MangaResult, ChapterResult, PageResult, SourceStatus
)


class MangaDexConnector(BaseConnector):
    """
    MangaDex API connector.
    
    This is the "safest" implementation that respects their rate limits
    to avoid getting banned again.
    """
    
    # =========================================================================
    # CONFIGURATION
    # =========================================================================
    
    id = "mangadex"
    name = "MangaDex"
    base_url = "https://api.mangadex.org"
    icon = "🥭"
    
    # CONSERVATIVE rate limiting - stay well below their 5/sec limit
    rate_limit = 2.0          # 2 requests per second
    rate_limit_burst = 3      # Small burst
    request_timeout = 20
    
    supports_latest = True
    supports_popular = True
    requires_cloudflare = False
    
    languages = ["en", "ja", "ko", "zh", "es", "fr", "de", "it", "pt-br", "ru"]
    
    # IMPORTANT: User-Agent must identify your app, NOT spoof a browser
    USER_AGENT = "MangaNegus/2.2 (https://github.com/bookers1897/Manga-Negus)"
    
    CONTENT_RATINGS = ["safe", "suggestive", "erotica"]
    
    # =========================================================================
    # REQUEST HELPERS
    # =========================================================================
    
    def _headers(self, for_images: bool = False) -> Dict[str, str]:
        """
        Get request headers.
        
        CRITICAL: Image requests must NOT include auth headers!
        This would leak your tokens to MD@Home volunteer nodes.
        """
        if for_images:
            return {
                "User-Agent": self.USER_AGENT,
                "Accept": "image/webp,image/png,image/jpeg,*/*"
            }
        return {
            "User-Agent": self.USER_AGENT,
            "Accept": "application/json"
        }
    
    def _request(
        self,
        endpoint: str,
        params: Optional[Dict] = None
    ) -> Optional[Dict]:
        """
        Make a rate-limited API request.
        
        Handles:
          - Rate limiting (429) -> Immediate cooldown, NO retry
          - Temporary ban (403) -> Long cooldown
          - Server errors (5xx) -> Track failures
        """
        if not self.session:
            return None
        
        # Wait for rate limit token BEFORE making request
        self._wait_for_rate_limit()
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = self.session.get(
                url,
                params=params,
                headers=self._headers(),
                timeout=self.request_timeout
            )
            
            # SUCCESS
            if response.status_code == 200:
                self._handle_success()
                return response.json()
            
            # RATE LIMITED - STOP IMMEDIATELY!
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                self._handle_rate_limit(retry_after)
                self._log(f"⚠️ MangaDex rate limit! Waiting {retry_after}s...")
                return None
            
            # BANNED - DO NOT RETRY!
            if response.status_code == 403:
                self._handle_cloudflare()
                self._log("🚫 MangaDex temporary ban! Switching to other sources...")
                return None
            
            # OTHER ERRORS
            self._handle_error(f"HTTP {response.status_code}")
            return None
            
        except Exception as e:
            self._handle_error(str(e))
            return None
    
    def _log(self, msg: str) -> None:
        """Log message to app's logging system."""
        try:
            from app import log
            log(msg)
        except:
            print(msg)
    
    # =========================================================================
    # PARSING HELPERS
    # =========================================================================
    
    def _extract_cover(self, manga_data: Dict) -> Optional[str]:
        """Extract cover URL from manga relationships."""
        manga_id = manga_data.get("id", "")
        
        for rel in manga_data.get("relationships", []):
            if rel.get("type") == "cover_art":
                filename = rel.get("attributes", {}).get("fileName")
                if filename:
                    # Use 256px thumbnail for speed
                    return f"https://uploads.mangadex.org/covers/{manga_id}/{filename}.256.jpg"
        return None
    
    def _parse_manga(self, data: Dict) -> MangaResult:
        """Parse MangaDex manga data into standardized MangaResult."""
        attrs = data.get("attributes", {})
        rels = data.get("relationships", [])
        
        # Get title (prefer English, fallback to romaji, then Japanese)
        titles = attrs.get("title", {})
        title = (
            titles.get("en") or
            titles.get("ja-ro") or
            titles.get("ja") or
            next(iter(titles.values()), "Unknown")
        )
        
        # Get description
        desc = attrs.get("description", {})
        description = desc.get("en", next(iter(desc.values()), None))
        
        # Get author from relationships
        author = None
        for rel in rels:
            if rel.get("type") == "author":
                author = rel.get("attributes", {}).get("name")
                break
        
        # Get genres from tags
        genres = []
        for tag in attrs.get("tags", []):
            tag_name = tag.get("attributes", {}).get("name", {})
            if isinstance(tag_name, dict):
                genres.append(tag_name.get("en", ""))
            elif isinstance(tag_name, str):
                genres.append(tag_name)
        
        return MangaResult(
            id=data.get("id", ""),
            title=title,
            source=self.id,
            cover_url=self._extract_cover(data),
            description=description,
            author=author,
            status=attrs.get("status"),
            url=f"https://mangadex.org/title/{data.get('id')}",
            genres=genres,
            year=attrs.get("year")
        )
    
    def _parse_chapter(self, data: Dict) -> ChapterResult:
        """Parse MangaDex chapter data into standardized ChapterResult."""
        attrs = data.get("attributes", {})
        
        # Get scanlation group
        scanlator = None
        for rel in data.get("relationships", []):
            if rel.get("type") == "scanlation_group":
                scanlator = rel.get("attributes", {}).get("name")
                break
        
        return ChapterResult(
            id=data.get("id", ""),
            chapter=attrs.get("chapter") or "0",
            title=attrs.get("title"),
            volume=attrs.get("volume"),
            language=attrs.get("translatedLanguage", "en"),
            pages=attrs.get("pages", 0),
            scanlator=scanlator,
            published=attrs.get("publishAt"),
            url=f"https://mangadex.org/chapter/{data.get('id')}",
            source=self.id
        )
    
    # =========================================================================
    # PUBLIC API METHODS
    # =========================================================================
    
    def search(self, query: str, page: int = 1) -> List[MangaResult]:
        """Search MangaDex for manga by title."""
        self._log(f"🔍 Searching MangaDex: {query}")
        
        limit = 15
        offset = (page - 1) * limit
        
        params = {
            "title": query,
            "limit": limit,
            "offset": offset,
            "includes[]": ["cover_art", "author"],
            "contentRating[]": self.CONTENT_RATINGS,
            "order[relevance]": "desc"
        }
        
        data = self._request("/manga", params)
        if not data:
            return []
        
        results = []
        for manga in data.get("data", []):
            try:
                results.append(self._parse_manga(manga))
            except Exception:
                continue
        
        self._log(f"✅ Found {len(results)} results")
        return results
    
    def get_popular(self, page: int = 1) -> List[MangaResult]:
        """Get most popular manga by follower count."""
        limit = 15
        offset = (page - 1) * limit
        
        params = {
            "limit": limit,
            "offset": offset,
            "includes[]": ["cover_art", "author"],
            "contentRating[]": self.CONTENT_RATINGS,
            "availableTranslatedLanguage[]": ["en"],
            "order[followedCount]": "desc"
        }
        
        data = self._request("/manga", params)
        if not data:
            return []
        
        return [self._parse_manga(m) for m in data.get("data", [])]
    
    def get_latest(self, page: int = 1) -> List[MangaResult]:
        """Get recently updated manga."""
        limit = 15
        offset = (page - 1) * limit
        
        params = {
            "limit": limit,
            "offset": offset,
            "includes[]": ["cover_art", "author"],
            "contentRating[]": self.CONTENT_RATINGS,
            "availableTranslatedLanguage[]": ["en"],
            "order[latestUploadedChapter]": "desc"
        }
        
        data = self._request("/manga", params)
        if not data:
            return []
        
        return [self._parse_manga(m) for m in data.get("data", [])]
    
    def get_chapters(
        self,
        manga_id: str,
        language: str = "en"
    ) -> List[ChapterResult]:
        """
        Get all chapters for a manga.
        
        Handles pagination (MangaDex limits to 100 per request)
        and deduplicates chapters from multiple scanlation groups.
        """
        self._log(f"📖 Fetching chapters from MangaDex...")
        
        all_chapters = []
        offset = 0
        limit = 100  # MangaDex max
        
        while True:
            params = {
                "manga": manga_id,
                "translatedLanguage[]": [language],
                "limit": limit,
                "offset": offset,
                "order[chapter]": "asc",
                "includes[]": ["scanlation_group"]
            }
            
            data = self._request("/chapter", params)
            if not data:
                break
            
            chapters = data.get("data", [])
            all_chapters.extend(chapters)
            
            # Check if we've fetched all
            total = data.get("total", 0)
            if offset + len(chapters) >= total or len(chapters) < limit:
                break
            
            offset += limit
            
            # Extra delay between pagination requests
            time.sleep(0.3)
        
        # Deduplicate by chapter number (keep first occurrence)
        unique = {}
        for ch in all_chapters:
            num = ch.get("attributes", {}).get("chapter", "0")
            if num and num not in unique:
                unique[num] = ch
        
        # Sort by chapter number
        sorted_chapters = sorted(
            unique.values(),
            key=lambda x: float(x.get("attributes", {}).get("chapter") or 0)
        )
        
        results = [self._parse_chapter(c) for c in sorted_chapters]
        self._log(f"✅ Found {len(results)} unique chapters")
        
        return results
    
    def get_pages(self, chapter_id: str) -> List[PageResult]:
        """
        Get page image URLs for a chapter.
        
        IMPORTANT: Must use /at-home/server/ endpoint!
        This returns geo-optimized CDN URLs that expire after 15 minutes.
        Never hardcode image URLs.
        """
        data = self._request(f"/at-home/server/{chapter_id}")
        if not data:
            return []
        
        base_url = data.get("baseUrl", "")
        chapter_data = data.get("chapter", {})
        hash_code = chapter_data.get("hash", "")
        filenames = chapter_data.get("data", [])
        
        pages = []
        for i, filename in enumerate(filenames):
            url = f"{base_url}/data/{hash_code}/{filename}"
            pages.append(PageResult(
                url=url,
                index=i,
                headers=self._headers(for_images=True),
                referer="https://mangadex.org/"
            ))
        
        return pages
    
    def get_manga_details(self, manga_id: str) -> Optional[MangaResult]:
        """Get full details for a specific manga."""
        params = {"includes[]": ["cover_art", "author", "artist"]}
        
        data = self._request(f"/manga/{manga_id}", params)
        if not data or "data" not in data:
            return None
        
        return self._parse_manga(data["data"])
