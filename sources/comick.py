"""
================================================================================
MangaNegus v2.3 - ComicK Connector (with curl_cffi Cloudflare bypass)
================================================================================
ComicK.io API connector - one of the best manga aggregators.

Benefits:
  - Large catalog (rivals MangaDex)
  - Fast and reliable API
  - Good English translations
  - Less strict rate limits than MangaDex
  - Proper English titles

Uses curl_cffi for industry-standard TLS fingerprint bypass.
================================================================================
"""

import time
import random
from typing import List, Optional, Dict, Any
from .base import (
    BaseConnector, MangaResult, ChapterResult, PageResult, SourceStatus, USER_AGENTS
)

# Try curl_cffi first (better Cloudflare bypass)
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


class ComicKConnector(BaseConnector):
    """
    ComicK.io API connector with Cloudflare bypass.
    Uses curl_cffi (preferred) or cloudscraper for TLS fingerprint bypass.

    Features:
      - User-agent rotation from pool
      - Exponential backoff retry (3 retries, 0.3 backoff factor)
      - 30 second timeout
      - Session persistence with cookie handling
    """

    # =========================================================================
    # CONFIGURATION
    # =========================================================================

    id = "comick"
    name = "ComicK"
    base_url = "https://api.comick.io"
    icon = "📚"

    rate_limit = 3.0          # 3 requests per second
    rate_limit_burst = 5
    request_timeout = 30

    supports_latest = True
    supports_popular = True
    requires_cloudflare = True

    languages = ["en", "ja", "ko", "zh", "es", "fr", "de", "it", "pt-br", "ru"]

    # Retry configuration
    MAX_RETRIES = 3
    BACKOFF_FACTOR = 0.3  # Exponential backoff: 0.3 * (2 ** attempt)

    def __init__(self):
        super().__init__()
        self._scraper = None
        self._curl_session = None
        self._init_scraper()

    def _init_scraper(self):
        """Initialize scraper session with best available method."""
        # Try curl_cffi first (better TLS fingerprint bypass)
        if HAS_CURL_CFFI:
            try:
                self._curl_session = curl_requests.Session(impersonate="chrome120")
                self._log("✅ ComicK curl_cffi bypass initialized")
                return
            except Exception as e:
                self._log(f"⚠️ curl_cffi failed: {e}")

        # Fallback to cloudscraper
        if HAS_CLOUDSCRAPER:
            try:
                self._scraper = cloudscraper.create_scraper(
                    browser={
                        'browser': 'chrome',
                        'platform': 'windows',
                        'mobile': False
                    }
                )
                self._log("✅ ComicK cloudscraper bypass initialized")
            except Exception as e:
                self._log(f"⚠️ Failed to initialize cloudscraper: {e}")
                self._scraper = None

    # =========================================================================
    # REQUEST HELPERS
    # =========================================================================

    def _headers(self) -> Dict[str, str]:
        """Get request headers."""
        return {
            "User-Agent": self.USER_AGENT,
            "Accept": "application/json",
            "Origin": "https://comick.io",
            "Referer": "https://comick.io/"
        }

    def _request(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        retries: int = 3
    ) -> Optional[Any]:
        """Make a rate-limited API request with retries."""
        # Use curl_cffi session if available (best Cloudflare bypass)
        session = self._curl_session or self._scraper or self.session
        if not session:
            return None
        if self.requires_cloudflare and not self._curl_session and not self._scraper:
            self._handle_cloudflare()
            self._log("⚠️ ComicK requires curl_cffi or cloudscraper for access")
            return None

        self._wait_for_rate_limit()

        url = f"{self.base_url}{endpoint}"

        for attempt in range(retries):
            try:
                response = session.get(
                    url,
                    params=params,
                    headers=self._headers(),
                    timeout=self.request_timeout
                )

                if response.status_code == 200:
                    self._handle_success()
                    return response.json()

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 30))
                    self._handle_rate_limit(retry_after)
                    self._log(f"⚠️ ComicK rate limit! Waiting {retry_after}s...")
                    if attempt < retries - 1:
                        time.sleep(retry_after)
                        continue
                    return None

                if response.status_code >= 500:
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

    def _log(self, msg: str) -> None:
        """Log message to app's logging system."""
        from sources.base import source_log
        source_log(msg)

    def get_download_session(self):
        """Prefer curl_cffi/cloudscraper sessions for downloads."""
        return self._curl_session or self._scraper or self.session

    # =========================================================================
    # PARSING HELPERS
    # =========================================================================

    def _get_english_title(self, comic: Dict) -> str:
        """
        Extract best English title from comic data.

        ComicK structure:
        - title: main title (usually English)
        - md_titles: array of alternate titles with lang codes
        """
        # Main title is usually English
        title = comic.get("title", "")
        if title:
            return title

        # Check md_titles for English
        md_titles = comic.get("md_titles", [])
        for t in md_titles:
            if isinstance(t, dict):
                if t.get("lang") == "en":
                    return t.get("title", "")

        # Fallback to slug
        slug = comic.get("slug", "")
        if slug:
            return slug.replace("-", " ").title()

        return "Unknown"

    def _parse_manga(self, comic: Dict) -> MangaResult:
        """Parse ComicK comic data into MangaResult."""
        # Get the best English title
        title = self._get_english_title(comic)

        # Get cover
        cover_url = None
        covers = comic.get("md_covers", [])
        if covers:
            # Get highest quality cover
            cover = covers[0] if covers else None
            if cover:
                b2key = cover.get("b2key", "")
                if b2key:
                    cover_url = f"https://meo.comick.pictures/{b2key}"

        # Get description
        desc = comic.get("desc", "") or comic.get("description", "")

        # Get genres
        genres = []
        for genre in comic.get("genres", []) or comic.get("md_comic_md_genres", []):
            if isinstance(genre, dict):
                name = genre.get("name") or genre.get("md_genres", {}).get("name", "")
                if name:
                    genres.append(name)
            elif isinstance(genre, str):
                genres.append(genre)

        # Get authors
        authors = comic.get("authors", []) or comic.get("md_authors", [])
        author = None
        if authors:
            if isinstance(authors[0], dict):
                author = authors[0].get("name", "")
            elif isinstance(authors[0], str):
                author = authors[0]

        # Get status
        status_map = {1: "ongoing", 2: "completed", 3: "cancelled", 4: "hiatus"}
        status = status_map.get(comic.get("status"), None)

        # Get hid (ComicK's unique ID)
        hid = comic.get("hid", "") or comic.get("slug", "")

        return MangaResult(
            id=hid,
            title=title,
            source=self.id,
            cover_url=cover_url,
            description=desc,
            author=author,
            status=status,
            url=f"https://comick.io/comic/{hid}",
            genres=genres,
            year=comic.get("year")
        )

    def _parse_chapter(self, chapter: Dict) -> ChapterResult:
        """Parse ComicK chapter data into ChapterResult."""
        return ChapterResult(
            id=chapter.get("hid", ""),
            chapter=str(chapter.get("chap", "0") or "0"),
            title=chapter.get("title"),
            volume=str(chapter.get("vol", "")) if chapter.get("vol") else None,
            language=chapter.get("lang", "en"),
            pages=chapter.get("count") or 0,
            scanlator=chapter.get("group_name"),
            published=chapter.get("created_at"),
            url=f"https://comick.io/chapter/{chapter.get('hid')}",
            source=self.id
        )

    # =========================================================================
    # PUBLIC API METHODS
    # =========================================================================

    def search(self, query: str, page: int = 1) -> List[MangaResult]:
        """Search ComicK for manga."""
        self._log(f"🔍 Searching ComicK: {query}")

        # ComicK uses offset-based pagination
        limit = 20
        offset = (page - 1) * limit

        params = {
            "q": query,
            "limit": limit,
            "page": page,
            "t": "true"  # Include tachiyomi-compatible results
        }

        data = self._request("/v1.0/search", params)
        if not data:
            return []

        results = []
        for comic in data:
            try:
                results.append(self._parse_manga(comic))
            except Exception as e:
                self._log(f"⚠️ Parse error: {e}")
                continue

        self._log(f"✅ Found {len(results)} results")
        return results

    def get_popular(self, page: int = 1) -> List[MangaResult]:
        """Get trending/popular manga."""
        params = {
            "page": page,
            "limit": 20,
            "order": "follow_count"
        }

        data = self._request("/v1.0/top", params)
        if not data:
            # Fallback to regular browse
            data = self._request("/v1.0/search", {"limit": 20, "page": page})

        if not data:
            return []

        # Handle both list and object responses
        comics = data if isinstance(data, list) else data.get("comics", data.get("md_comics", []))

        results = []
        for comic in comics:
            try:
                results.append(self._parse_manga(comic))
            except Exception as e:

                self._log(f"Failed to parse item: {e}")

                continue

        return results

    def get_latest(self, page: int = 1) -> List[MangaResult]:
        """Get recently updated manga."""
        params = {
            "page": page,
            "limit": 20,
            "order": "uploaded"
        }

        # Get latest chapters and extract unique manga
        data = self._request("/v1.0/chapter", params)
        if not data:
            return []

        # Extract unique manga from chapters
        seen = set()
        results = []
        chapters = data if isinstance(data, list) else data.get("chapters", [])

        for ch in chapters:
            comic = ch.get("md_comics") or ch.get("comic")
            if not comic:
                continue

            hid = comic.get("hid", "")
            if hid in seen:
                continue
            seen.add(hid)

            try:
                results.append(self._parse_manga(comic))
            except Exception as e:

                self._log(f"Failed to parse item: {e}")

                continue

            if len(results) >= 20:
                break

        return results

    def get_chapters(
        self,
        manga_id: str,
        language: str = "en"
    ) -> List[ChapterResult]:
        """
        Get ALL chapters for a manga.

        ComicK allows fetching all chapters in one request with proper params.
        """
        self._log(f"📖 Fetching chapters from ComicK...")

        all_chapters = []
        page = 1
        limit = 300  # ComicK allows larger limits

        while True:
            params = {
                "limit": limit,
                "page": page,
                "lang": language,
                "chap-order": 1  # Ascending order
            }

            self._log(f"📖 Fetching page {page}...")
            data = self._request(f"/comic/{manga_id}/chapters", params)

            if not data:
                break

            chapters = data.get("chapters", [])
            if not chapters:
                break

            all_chapters.extend(chapters)
            self._log(f"📖 Fetched {len(chapters)} chapters (total: {len(all_chapters)})")

            # Check if there are more pages
            total = data.get("total", 0)
            if len(all_chapters) >= total or len(chapters) < limit:
                break

            page += 1
            time.sleep(0.3)  # Rate limit between pages

        # Deduplicate by chapter number
        unique = {}
        for ch in all_chapters:
            num = str(ch.get("chap", "0") or "0")
            if num not in unique:
                unique[num] = ch

        # Sort by chapter number
        sorted_chapters = sorted(
            unique.values(),
            key=lambda x: float(x.get("chap") or 0) if str(x.get("chap", "0")).replace(".", "").isdigit() else 0
        )

        results = [self._parse_chapter(c) for c in sorted_chapters]
        self._log(f"✅ Found {len(results)} unique chapters")

        return results

    def get_pages(self, chapter_id: str) -> List[PageResult]:
        """Get page images for a chapter."""
        data = self._request(f"/chapter/{chapter_id}")
        if not data:
            return []

        chapter = data.get("chapter", data)
        images = chapter.get("images", []) or chapter.get("md_images", [])

        pages = []
        for i, img in enumerate(images):
            # ComicK uses b2key for image URLs
            if isinstance(img, dict):
                b2key = img.get("b2key", "") or img.get("name", "")
            else:
                b2key = str(img)

            if b2key:
                url = f"https://meo.comick.pictures/{b2key}"
                pages.append(PageResult(
                    url=url,
                    index=i,
                    headers={
                        "Referer": "https://comick.io/",
                        "User-Agent": self.USER_AGENT
                    },
                    referer="https://comick.io/"
                ))

        return pages

    def get_manga_details(self, manga_id: str) -> Optional[MangaResult]:
        """Get detailed manga info."""
        data = self._request(f"/comic/{manga_id}")
        if not data:
            return None

        comic = data.get("comic", data)
        return self._parse_manga(comic)
