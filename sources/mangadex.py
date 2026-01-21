"""
================================================================================
MangaNegus v2.3 - MangaDex Connector (Improved)
================================================================================
MangaDex API v5 connector with PROPER rate limiting and English title support.

FIXES IN THIS VERSION:
  - Proper English title extraction (fallback to romaji, then Japanese)
  - Fixed chapter pagination - fetches ALL chapters properly
  - Better error handling and logging
  - Improved rate limiting with exponential backoff
================================================================================
"""

import time
from typing import List, Optional, Dict, Any
from .base import (
    BaseConnector, MangaResult, ChapterResult, PageResult, SourceStatus
)


class MangaDexConnector(BaseConnector):
    """
    MangaDex API connector with improved title handling.
    """

    # =========================================================================
    # CONFIGURATION
    # =========================================================================

    id = "mangadex"
    name = "MangaDex"
    base_url = "https://api.mangadex.org"
    icon = "🥭"
    
    # URL Detection patterns
    url_patterns = [
        r'https?://(?:www\.)?mangadex\.org/title/([a-f0-9-]+)',  # UUID format
    ]

    # Rate limiting - MangaDex allows 5/sec, we use 3/sec for safety
    rate_limit = 3.0          # 3 requests per second
    rate_limit_burst = 5      # Reasonable burst
    request_timeout = 30      # Increased timeout

    supports_latest = True
    supports_popular = True
    requires_cloudflare = False

    languages = ["en", "ja", "ko", "zh", "es", "fr", "de", "it", "pt-br", "ru"]

    # IMPORTANT: User-Agent must identify your app, NOT spoof a browser
    USER_AGENT = "MangaNegus/2.3 (https://github.com/bookers1897/Manga-Negus)"

    CONTENT_RATINGS = ["safe", "suggestive", "erotica"]

    # =========================================================================
    # REQUEST HELPERS
    # =========================================================================

    def _headers(self, for_images: bool = False) -> Dict[str, str]:
        """Get request headers."""
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
        params: Optional[Dict] = None,
        retries: int = 3
    ) -> Optional[Dict]:
        """
        Make a rate-limited API request with retries.
        """
        if not self.session:
            return None

        # Wait for rate limit token BEFORE making request
        self._wait_for_rate_limit()

        url = f"{self.base_url}{endpoint}"

        for attempt in range(retries):
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
                    if attempt < retries - 1:
                        time.sleep(retry_after)
                        continue
                    return None

                # BANNED - DO NOT RETRY!
                if response.status_code == 403:
                    self._handle_cloudflare()
                    self._log("🚫 MangaDex temporary ban! Try again later...")
                    return None

                # OTHER ERRORS - Retry with backoff
                if response.status_code >= 500:
                    if attempt < retries - 1:
                        wait = (2 ** attempt) + 1
                        self._log(f"⚠️ MangaDex server error, retrying in {wait}s...")
                        time.sleep(wait)
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

    # =========================================================================
    # TITLE EXTRACTION (FIXED)
    # =========================================================================

    def _get_english_title(self, manga_data: Dict) -> str:
        """
        Extract the best English title from manga data.

        Priority:
        1. English title (altTitles or main title)
        2. Romaji title (ja-ro)
        3. Japanese title
        4. Any available title
        """
        attrs = manga_data.get("attributes", {})
        titles = attrs.get("title", {})
        alt_titles = attrs.get("altTitles", [])

        # Check main title for English
        if "en" in titles:
            return titles["en"]

        # Check alternate titles for English
        for alt in alt_titles:
            if isinstance(alt, dict) and "en" in alt:
                return alt["en"]

        # Try romaji (Japanese romanized)
        if "ja-ro" in titles:
            return titles["ja-ro"]

        for alt in alt_titles:
            if isinstance(alt, dict) and "ja-ro" in alt:
                return alt["ja-ro"]

        # Try Japanese
        if "ja" in titles:
            return titles["ja"]

        # Fallback to any available title
        if titles:
            return next(iter(titles.values()))

        # Last resort: check alt titles
        for alt in alt_titles:
            if isinstance(alt, dict):
                return next(iter(alt.values()), "Unknown")

        return "Unknown"

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

        # Get best English title
        title = self._get_english_title(data)

        # Get description (prefer English)
        desc = attrs.get("description", {})
        description = desc.get("en") if isinstance(desc, dict) else None
        if not description and isinstance(desc, dict):
            description = next(iter(desc.values()), None)

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

        # Get alternate titles
        alt_titles = []
        for alt in attrs.get("altTitles", []):
            if isinstance(alt, dict):
                for lang, t in alt.items():
                    if t and t != title:
                        alt_titles.append(t)

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
            alt_titles=alt_titles[:5],  # Limit to 5
            year=attrs.get("year")
        )

    def _parse_chapter(self, data: Dict) -> ChapterResult:
        """Parse MangaDex chapter data into standardized ChapterResult."""
        attrs = data.get("attributes", {})
        if attrs.get("externalUrl"):
            return None

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
            except Exception as e:
                self._log(f"⚠️ Parse error: {e}")
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
        Get ALL chapters for a manga with proper pagination.

        FIXED: Now properly handles pagination to get ALL chapters,
        not just the first 100.
        """
        self._log(f"📖 Fetching chapters from MangaDex...")

        all_chapters = []
        offset = 0
        limit = 100  # MangaDex max per request
        total = None

        while True:
            params = {
                "manga": manga_id,
                "translatedLanguage[]": [language],
                "limit": limit,
                "offset": offset,
                "order[chapter]": "asc",
                "includes[]": ["scanlation_group"],
                "contentRating[]": self.CONTENT_RATINGS
            }

            self._log(f"📖 Fetching chapters {offset} to {offset + limit}...")
            data = self._request("/chapter", params)

            if not data:
                self._log(f"⚠️ Failed to fetch chapters at offset {offset}")
                break

            chapters = data.get("data", [])
            all_chapters.extend(chapters)

            # Get total from first response
            if total is None:
                total = data.get("total", 0)
                self._log(f"📖 Total chapters available: {total}")

            # Check if we've fetched all
            fetched = offset + len(chapters)
            if fetched >= total or len(chapters) < limit:
                break

            offset += limit

            # Rate limit between pagination requests
            time.sleep(0.5)

        self._log(f"📖 Fetched {len(all_chapters)} raw chapters")

        # Deduplicate by chapter number (keep first occurrence)
        unique = {}
        for ch in all_chapters:
            num = ch.get("attributes", {}).get("chapter")
            if num is None:
                num = "0"
            # Use chapter + scanlator as key to keep one per group
            key = str(num)
            if key not in unique:
                unique[key] = ch

        # Sort by chapter number
        def sort_key(x):
            ch = x.get("attributes", {}).get("chapter")
            try:
                return float(ch) if ch else 0
            except (ValueError, TypeError):
                return 0

        sorted_chapters = sorted(unique.values(), key=sort_key)

        results = []
        for ch in sorted_chapters:
            parsed = self._parse_chapter(ch)
            if parsed is not None:
                results.append(parsed)
        self._log(f"✅ Found {len(results)} unique chapters")

        return results

    def get_pages(self, chapter_id: str) -> List[PageResult]:
        """
        Get page image URLs for a chapter.

        Uses /at-home/server/ endpoint for geo-optimized CDN URLs.
        """
        data = self._request(f"/at-home/server/{chapter_id}")
        if not data:
            return []

        base_url = data.get("baseUrl", "")
        chapter_data = data.get("chapter", {})
        hash_code = chapter_data.get("hash", "")
        filenames = chapter_data.get("data", [])
        if not filenames:
            filenames = chapter_data.get("dataSaver", [])

        if not base_url or not hash_code:
            self._handle_error("Missing baseUrl or hash for chapter pages")
            return []

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
