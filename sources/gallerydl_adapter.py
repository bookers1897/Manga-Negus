"""
================================================================================
MangaNegus v2.3 - Gallery-DL Adapter
================================================================================
Universal connector that wraps gallery-dl library to provide access to 15+
manga sources through a single interface.

SUPPORTED EXTRACTORS (manga-related):
  - mangadex, mangakakalot, mangasee, mangapark, manganelo
  - webtoon (Korean/English), tapas, dynasty-scans
  - nhentai, e-hentai, exhentai (adult)
  - imgur (for manga hosted there)
  - And more via gallery-dl's extractor system

USAGE:
    This adapter creates "virtual" sources for each gallery-dl extractor.
    Each extractor becomes a selectable source in the MangaNegus UI.

ADVANTAGES:
  1. Single dependency (gallery-dl) provides 15+ sources
  2. Actively maintained by gallery-dl community
  3. Handles anti-bot measures internally
  4. Consistent extraction patterns

LIMITATIONS:
  - Search may not work for all extractors (some need direct URLs)
  - Some extractors require cookies/authentication
  - Rate limiting is per-adapter, not per-extractor
================================================================================
"""

import re
import subprocess
import json
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from .base import (
    BaseConnector,
    MangaResult,
    ChapterResult,
    PageResult,
    SourceStatus,
    source_log
)


# =============================================================================
# GALLERY-DL EXTRACTOR CONFIGURATIONS
# =============================================================================

@dataclass
class ExtractorConfig:
    """Configuration for a gallery-dl extractor."""
    name: str                    # Display name
    icon: str                    # Emoji icon
    domain: str                  # Primary domain
    search_url: Optional[str]    # Search URL template (if supported)
    manga_url_pattern: str       # Regex to identify manga URLs
    supports_search: bool = False
    requires_auth: bool = False
    is_adult: bool = False


# Extractors that gallery-dl supports for manga
GALLERY_DL_EXTRACTORS: Dict[str, ExtractorConfig] = {
    "gdl-mangadex": ExtractorConfig(
        name="MangaDex (GDL)",
        icon="",
        domain="mangadex.org",
        search_url="https://mangadex.org/search?q={query}",
        manga_url_pattern=r"mangadex\.org/title/([a-f0-9-]+)",
        supports_search=True
    ),
    "gdl-mangakakalot": ExtractorConfig(
        name="MangaKakalot (GDL)",
        icon="",
        domain="mangakakalot.com",
        search_url="https://mangakakalot.com/search/story/{query}",
        manga_url_pattern=r"mangakakalot\.com/manga/(\w+)",
        supports_search=True
    ),
    "gdl-mangasee": ExtractorConfig(
        name="MangaSee (GDL)",
        icon="",
        domain="mangasee123.com",
        search_url="https://mangasee123.com/search/?name={query}",
        manga_url_pattern=r"mangasee123\.com/manga/([^/]+)",
        supports_search=True
    ),
    "gdl-mangapark": ExtractorConfig(
        name="MangaPark (GDL)",
        icon="",
        domain="mangapark.net",
        search_url="https://mangapark.net/search?word={query}",
        manga_url_pattern=r"mangapark\.net/title/(\d+)",
        supports_search=True
    ),
    "gdl-webtoon": ExtractorConfig(
        name="Webtoon (GDL)",
        icon="",
        domain="webtoons.com",
        search_url=None,  # Webtoon search requires JavaScript
        manga_url_pattern=r"webtoons\.com/.+/([^/]+)/list",
        supports_search=False
    ),
    "gdl-tapas": ExtractorConfig(
        name="Tapas (GDL)",
        icon="",
        domain="tapas.io",
        search_url="https://tapas.io/search?q={query}",
        manga_url_pattern=r"tapas\.io/series/([^/]+)",
        supports_search=True
    ),
    "gdl-dynasty": ExtractorConfig(
        name="Dynasty Scans (GDL)",
        icon="",
        domain="dynasty-scans.com",
        search_url="https://dynasty-scans.com/search?q={query}",
        manga_url_pattern=r"dynasty-scans\.com/series/([^/]+)",
        supports_search=True
    ),
    "gdl-imgur": ExtractorConfig(
        name="Imgur Albums (GDL)",
        icon="",
        domain="imgur.com",
        search_url=None,
        manga_url_pattern=r"imgur\.com/a/(\w+)",
        supports_search=False
    ),
}


# =============================================================================
# GALLERY-DL ADAPTER (BASE CLASS)
# =============================================================================

class GalleryDLAdapter(BaseConnector):
    """
    Adapter that wraps gallery-dl for manga extraction.

    This provides a universal interface to gallery-dl's extractors,
    allowing MangaNegus to use any site that gallery-dl supports.

    ARCHITECTURE:
        GalleryDLAdapter.search() -> gallery-dl CLI -> JSON output -> MangaResult

    NOTE: This uses subprocess calls to gallery-dl CLI rather than the Python API
    because the CLI is more stable and handles edge cases better.
    """

    # Override in subclass or set via constructor
    id: str = "gallerydl"
    name: str = "Gallery-DL"
    base_url: str = ""
    icon: str = ""

    # Gallery-dl specific
    extractor_config: Optional[ExtractorConfig] = None

    # Rate limiting (conservative to avoid bans)
    rate_limit: float = 1.0
    rate_limit_burst: int = 3
    request_timeout: int = 30

    supports_search: bool = False

    def __init__(self, extractor_id: Optional[str] = None):
        """
        Initialize the adapter.

        Args:
            extractor_id: ID of the extractor to use (e.g., "gdl-mangadex")
        """
        super().__init__()

        if extractor_id and extractor_id in GALLERY_DL_EXTRACTORS:
            config = GALLERY_DL_EXTRACTORS[extractor_id]
            self.id = extractor_id
            self.name = config.name
            self.icon = config.icon
            self.base_url = f"https://{config.domain}"
            self.extractor_config = config
            self.supports_search = config.supports_search

        # Check if gallery-dl is available
        self._gallerydl_available = self._check_gallerydl()

    def _check_gallerydl(self) -> bool:
        """Check if gallery-dl is installed and accessible."""
        try:
            result = subprocess.run(
                ["gallery-dl", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    def _run_gallerydl(
        self,
        url: str,
        options: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Run gallery-dl and return extracted data.

        Args:
            url: URL to extract
            options: Additional CLI options

        Returns:
            Extracted data as dictionary, or None on failure
        """
        if not self._gallerydl_available:
            source_log(f"[{self.id}] gallery-dl not available")
            return None

        self._wait_for_rate_limit()

        cmd = [
            "gallery-dl",
            "--dump-json",      # Output as JSON
            "--no-download",    # Don't download files
            url
        ]

        if options:
            cmd.extend(options)

        try:
            source_log(f"[{self.id}] Extracting: {url}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.request_timeout
            )

            if result.returncode != 0:
                if "429" in result.stderr or "rate" in result.stderr.lower():
                    self._handle_rate_limit(120)
                elif "cloudflare" in result.stderr.lower():
                    self._handle_cloudflare()
                else:
                    self._handle_error(result.stderr[:200])
                return None

            # Parse JSON output (gallery-dl outputs one JSON object per line)
            data = []
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    try:
                        data.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

            self._handle_success()
            return {"items": data} if data else None

        except subprocess.TimeoutExpired:
            self._handle_error("Request timed out")
            return None
        except Exception as e:
            self._handle_error(str(e))
            return None

    # =========================================================================
    # BASECONNECTOR INTERFACE IMPLEMENTATION
    # =========================================================================

    def search(self, query: str, page: int = 1) -> List[MangaResult]:
        """
        Search for manga using gallery-dl.

        Note: Not all extractors support search. For those that don't,
        users need to paste direct manga URLs.
        """
        if not self.extractor_config or not self.extractor_config.supports_search:
            source_log(f"[{self.id}] Search not supported - use direct URL")
            return []

        if not self.extractor_config.search_url:
            return []

        # Build search URL
        search_url = self.extractor_config.search_url.format(
            query=query.replace(" ", "+")
        )

        # For sites that gallery-dl can search
        data = self._run_gallerydl(search_url)

        if not data or "items" not in data:
            return []

        results = []
        for item in data["items"][:20]:  # Limit to 20 results
            result = self._parse_manga_result(item)
            if result:
                results.append(result)

        return results

    def get_chapters(
        self,
        manga_id: str,
        language: str = "en"
    ) -> List[ChapterResult]:
        """
        Get chapters for a manga.

        Args:
            manga_id: This can be either:
                - A URL (https://mangadex.org/title/xxx)
                - A source-specific ID
        """
        # If manga_id is a URL, use it directly
        if manga_id.startswith("http"):
            url = manga_id
        else:
            # Build URL from ID based on extractor
            url = self._build_manga_url(manga_id)

        if not url:
            return []

        data = self._run_gallerydl(url)

        if not data or "items" not in data:
            return []

        chapters = []
        for idx, item in enumerate(data["items"]):
            chapter = self._parse_chapter_result(item, idx)
            if chapter:
                chapters.append(chapter)

        # Sort by chapter number
        chapters.sort(key=lambda c: self._parse_chapter_number(c.chapter))

        return chapters

    def get_pages(self, chapter_id: str) -> List[PageResult]:
        """
        Get page images for a chapter.

        Args:
            chapter_id: Chapter URL or identifier
        """
        if chapter_id.startswith("http"):
            url = chapter_id
        else:
            # This shouldn't happen normally - chapters should have URLs
            source_log(f"[{self.id}] Invalid chapter ID: {chapter_id}")
            return []

        data = self._run_gallerydl(url)

        if not data or "items" not in data:
            return []

        pages = []
        for idx, item in enumerate(data["items"]):
            page = self._parse_page_result(item, idx)
            if page:
                pages.append(page)

        return pages

    # =========================================================================
    # PARSING HELPERS
    # =========================================================================

    def _parse_manga_result(self, item: Dict[str, Any]) -> Optional[MangaResult]:
        """Parse gallery-dl output into MangaResult."""
        try:
            # Gallery-dl output varies by extractor, handle common patterns
            manga_id = item.get("manga_id") or item.get("gallery_id") or item.get("id", "")
            title = item.get("manga") or item.get("title") or item.get("gallery", "")

            if not manga_id or not title:
                return None

            return MangaResult(
                id=str(manga_id),
                title=str(title),
                source=self.id,
                cover_url=item.get("cover") or item.get("thumbnail"),
                description=item.get("description"),
                author=item.get("author") or item.get("artist"),
                artist=item.get("artist"),
                status=item.get("status"),
                url=item.get("url") or item.get("manga_url"),
                genres=item.get("tags", []) or item.get("genres", []),
                year=item.get("date", {}).get("year") if isinstance(item.get("date"), dict) else None
            )
        except Exception as e:
            source_log(f"[{self.id}] Parse error: {e}")
            return None

    def _parse_chapter_result(
        self,
        item: Dict[str, Any],
        index: int
    ) -> Optional[ChapterResult]:
        """Parse gallery-dl output into ChapterResult."""
        try:
            chapter_id = item.get("chapter_id") or item.get("id") or str(index)
            chapter_num = item.get("chapter") or item.get("chapter_string") or str(index + 1)

            return ChapterResult(
                id=item.get("chapter_url") or str(chapter_id),
                chapter=str(chapter_num),
                title=item.get("chapter_title") or item.get("title"),
                volume=str(item.get("volume", "")) if item.get("volume") else None,
                language=item.get("language", "en") or "en",
                pages=item.get("count", 0),
                scanlator=item.get("group") or item.get("scanlator"),
                published=item.get("date"),
                url=item.get("chapter_url") or item.get("url"),
                source=self.id
            )
        except Exception as e:
            source_log(f"[{self.id}] Chapter parse error: {e}")
            return None

    def _parse_page_result(
        self,
        item: Dict[str, Any],
        index: int
    ) -> Optional[PageResult]:
        """Parse gallery-dl output into PageResult."""
        try:
            # Gallery-dl usually outputs direct image URLs
            url = item.get("url") or item.get("file_url") or item.get("image")

            if not url:
                return None

            return PageResult(
                url=url,
                index=item.get("page", index) or index,
                headers=item.get("_http_headers", {}),
                referer=item.get("referer")
            )
        except Exception as e:
            source_log(f"[{self.id}] Page parse error: {e}")
            return None

    def _build_manga_url(self, manga_id: str) -> Optional[str]:
        """Build manga URL from ID based on extractor config."""
        if not self.extractor_config:
            return None

        domain = self.extractor_config.domain

        # Common URL patterns by extractor
        if "mangadex" in self.id:
            return f"https://mangadex.org/title/{manga_id}"
        elif "mangakakalot" in self.id:
            return f"https://mangakakalot.com/manga/{manga_id}"
        elif "mangasee" in self.id:
            return f"https://mangasee123.com/manga/{manga_id}"
        elif "mangapark" in self.id:
            return f"https://mangapark.net/title/{manga_id}"
        elif "webtoon" in self.id:
            # Webtoon needs full URL
            return manga_id if manga_id.startswith("http") else None
        elif "tapas" in self.id:
            return f"https://tapas.io/series/{manga_id}"
        elif "dynasty" in self.id:
            return f"https://dynasty-scans.com/series/{manga_id}"

        return None

    @staticmethod
    def _parse_chapter_number(chapter: str) -> float:
        """Parse chapter string to sortable number."""
        try:
            # Handle formats like "10.5", "10", "Chapter 10"
            match = re.search(r"(\d+(?:\.\d+)?)", str(chapter))
            if match:
                return float(match.group(1))
            return 0.0
        except (ValueError, TypeError):
            return 0.0


# =============================================================================
# CONCRETE ADAPTER CLASSES (for auto-discovery)
# =============================================================================
# These classes are auto-discovered by SourceManager because they have
# no-argument constructors and inherit from BaseConnector.

class GDLMangaKakalot(GalleryDLAdapter):
    """MangaKakalot via gallery-dl."""
    def __init__(self):
        super().__init__("gdl-mangakakalot")


class GDLMangaSee(GalleryDLAdapter):
    """MangaSee via gallery-dl."""
    def __init__(self):
        super().__init__("gdl-mangasee")


class GDLMangaPark(GalleryDLAdapter):
    """MangaPark via gallery-dl."""
    def __init__(self):
        super().__init__("gdl-mangapark")


class GDLWebtoon(GalleryDLAdapter):
    """Webtoon via gallery-dl."""
    def __init__(self):
        super().__init__("gdl-webtoon")


class GDLTapas(GalleryDLAdapter):
    """Tapas via gallery-dl."""
    def __init__(self):
        super().__init__("gdl-tapas")


class GDLDynasty(GalleryDLAdapter):
    """Dynasty Scans via gallery-dl."""
    def __init__(self):
        super().__init__("gdl-dynasty")


class GDLImgur(GalleryDLAdapter):
    """Imgur Albums via gallery-dl."""
    def __init__(self):
        super().__init__("gdl-imgur")


# NOTE: We skip gdl-mangadex since we already have a native MangaDex connector
# that's more optimized. The GDL version would be redundant.


# =============================================================================
# DIRECT URL HANDLER (Universal)
# =============================================================================

class GalleryDLUniversal(BaseConnector):
    """
    Universal gallery-dl handler for direct URLs.

    This special connector accepts any URL that gallery-dl supports,
    allowing users to paste URLs from any supported site.

    Use case:
        User pastes: https://webtoons.com/en/fantasy/tower-of-god/list
        This connector detects it's a webtoon and extracts using gallery-dl.
    """

    id = "gdl-universal"
    name = "Direct URL (Gallery-DL)"
    icon = ""
    base_url = ""

    supports_search = False
    supports_latest = False
    supports_popular = False

    rate_limit = 1.0
    rate_limit_burst = 5

    def __init__(self):
        super().__init__()
        self._adapter = GalleryDLAdapter()
        self._gallerydl_available = self._adapter._gallerydl_available

    def search(self, query: str, page: int = 1) -> List[MangaResult]:
        """
        'Search' by accepting a direct URL.

        If the query looks like a URL, treat it as a direct manga URL.
        """
        if not query.startswith("http"):
            source_log(f"[{self.id}] Enter a full URL (https://...)")
            return []

        # Extract manga info from URL
        data = self._adapter._run_gallerydl(query)

        if not data or "items" not in data:
            return []

        # Try to extract manga metadata from first item
        if data["items"]:
            item = data["items"][0]
            result = MangaResult(
                id=query,  # Use URL as ID
                title=item.get("manga") or item.get("title") or "Unknown",
                source=self.id,
                cover_url=item.get("cover") or item.get("thumbnail"),
                description=item.get("description"),
                author=item.get("author"),
                url=query
            )
            return [result]

        return []

    def get_chapters(
        self,
        manga_id: str,
        language: str = "en"
    ) -> List[ChapterResult]:
        """Get chapters from URL."""
        return self._adapter.get_chapters(manga_id, language)

    def get_pages(self, chapter_id: str) -> List[PageResult]:
        """Get pages from chapter URL."""
        return self._adapter.get_pages(chapter_id)
