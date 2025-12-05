"""
================================================================================
MangaNegus v2.3 - MangaNato Connector (via Enma)
================================================================================
Uses the Enma library for unified access to MangaNato/Manganelo.

Benefits of this source:
  - Large catalog with fast updates
  - No strict rate limits
  - Good English translations
  - Reliable image servers
================================================================================
"""

import time
from typing import List, Optional, Dict, Any
from .base import (
    BaseConnector, MangaResult, ChapterResult, PageResult, SourceStatus
)

# Try to import Enma
try:
    from enma import Enma, Sources
    ENMA_AVAILABLE = True
except ImportError:
    ENMA_AVAILABLE = False


class MangaNatoConnector(BaseConnector):
    """
    MangaNato connector using the Enma library.
    """

    # =========================================================================
    # CONFIGURATION
    # =========================================================================

    id = "manganato"
    name = "MangaNato"
    base_url = "https://manganato.com"
    icon = "📖"

    rate_limit = 3.0          # 3 requests per second
    rate_limit_burst = 5
    request_timeout = 30

    supports_latest = True
    supports_popular = True
    requires_cloudflare = False

    languages = ["en"]

    def __init__(self):
        super().__init__()
        self._enma = None
        self._init_enma()

    def _init_enma(self):
        """Initialize Enma with MangaNato source."""
        if not ENMA_AVAILABLE:
            self._log("⚠️ Enma library not installed. Run: pip install enma")
            return

        try:
            self._enma = Enma()
            # Set source to manganato
            self._enma.source_manager.set_source(Sources.MANGANATO)
            self._log("✅ MangaNato source initialized via Enma")
        except Exception as e:
            self._log(f"⚠️ Failed to initialize Enma: {e}")
            self._enma = None

    def _log(self, msg: str) -> None:
        """Log message to app's logging system."""
        from sources.base import source_log
        source_log(msg)

    # =========================================================================
    # PARSING HELPERS
    # =========================================================================

    def _manga_to_result(self, manga: Any) -> MangaResult:
        """Convert Enma manga object to MangaResult."""
        # Handle both search results and full manga objects
        manga_id = getattr(manga, 'id', '') or getattr(manga, 'identifier', '')
        title = getattr(manga, 'title', {})

        # Handle title object or string
        if isinstance(title, dict):
            title_str = title.get('english') or title.get('romaji') or title.get('native') or 'Unknown'
        else:
            title_str = str(title) if title else 'Unknown'

        cover = getattr(manga, 'cover', None)
        if hasattr(cover, 'uri'):
            cover = cover.uri
        elif isinstance(cover, str):
            pass
        else:
            cover = None

        # Get authors
        authors = getattr(manga, 'authors', [])
        author_str = None
        if authors:
            if isinstance(authors[0], str):
                author_str = authors[0]
            elif hasattr(authors[0], 'name'):
                author_str = authors[0].name

        # Get genres
        genres = []
        manga_genres = getattr(manga, 'genres', [])
        for g in manga_genres:
            if isinstance(g, str):
                genres.append(g)
            elif hasattr(g, 'name'):
                genres.append(g.name)

        return MangaResult(
            id=str(manga_id),
            title=title_str,
            source=self.id,
            cover_url=cover,
            description=getattr(manga, 'description', None),
            author=author_str,
            status=getattr(manga, 'status', None),
            url=getattr(manga, 'url', None),
            genres=genres
        )

    def _chapter_to_result(self, chapter: Any, index: int = 0) -> ChapterResult:
        """Convert Enma chapter object to ChapterResult."""
        chapter_id = getattr(chapter, 'id', '') or str(index)
        chapter_num = getattr(chapter, 'chapter', str(index))

        # Try to extract chapter number from title if not available
        title = getattr(chapter, 'title', None)
        if not chapter_num and title:
            import re
            match = re.search(r'chapter\s*(\d+(?:\.\d+)?)', title.lower())
            if match:
                chapter_num = match.group(1)

        return ChapterResult(
            id=str(chapter_id),
            chapter=str(chapter_num) if chapter_num else str(index),
            title=title,
            language="en",
            pages=getattr(chapter, 'pages', 0),
            published=getattr(chapter, 'updated_at', None),
            url=getattr(chapter, 'url', None),
            source=self.id
        )

    # =========================================================================
    # PUBLIC API METHODS
    # =========================================================================

    def search(self, query: str, page: int = 1) -> List[MangaResult]:
        """Search MangaNato for manga."""
        if not self._enma:
            self._log("⚠️ MangaNato not available (Enma not initialized)")
            return []

        self._log(f"🔍 Searching MangaNato: {query}")
        self._wait_for_rate_limit()

        try:
            # Use Enma's search
            result = self._enma.search(query, page=page)

            if not result or not hasattr(result, 'results'):
                return []

            mangas = []
            for manga in result.results:
                try:
                    mangas.append(self._manga_to_result(manga))
                except Exception as e:
                    self._log(f"⚠️ Parse error: {e}")
                    continue

            self._handle_success()
            self._log(f"✅ Found {len(mangas)} results")
            return mangas

        except Exception as e:
            self._handle_error(str(e))
            self._log(f"❌ Search failed: {e}")
            return []

    def get_popular(self, page: int = 1) -> List[MangaResult]:
        """Get popular manga from MangaNato."""
        if not self._enma:
            return []

        self._wait_for_rate_limit()

        try:
            # Enma's paginate returns popular/trending manga
            result = self._enma.paginate(page=page)

            if not result or not hasattr(result, 'results'):
                return []

            mangas = []
            for manga in result.results:
                try:
                    mangas.append(self._manga_to_result(manga))
                except Exception:
                    continue

            self._handle_success()
            return mangas

        except Exception as e:
            self._handle_error(str(e))
            return []

    def get_latest(self, page: int = 1) -> List[MangaResult]:
        """Get latest manga - uses paginate as fallback."""
        return self.get_popular(page)

    def get_chapters(
        self,
        manga_id: str,
        language: str = "en"
    ) -> List[ChapterResult]:
        """Get all chapters for a manga."""
        if not self._enma:
            return []

        self._log(f"📖 Fetching chapters from MangaNato...")
        self._wait_for_rate_limit()

        try:
            # Get full manga details with chapters
            manga = self._enma.get(identifier=manga_id)

            if not manga:
                self._log("⚠️ Manga not found")
                return []

            chapters = getattr(manga, 'chapters', [])
            self._log(f"📖 Found {len(chapters)} chapters")

            results = []
            for i, ch in enumerate(chapters):
                try:
                    results.append(self._chapter_to_result(ch, i))
                except Exception:
                    continue

            # Sort by chapter number
            results.sort(key=lambda x: float(x.chapter) if x.chapter.replace('.', '').isdigit() else 0)

            self._handle_success()
            self._log(f"✅ Processed {len(results)} chapters")
            return results

        except Exception as e:
            self._handle_error(str(e))
            self._log(f"❌ Failed to get chapters: {e}")
            return []

    def get_pages(self, chapter_id: str) -> List[PageResult]:
        """Get page images for a chapter."""
        if not self._enma:
            return []

        self._wait_for_rate_limit()

        try:
            # Enma can fetch chapter pages
            # The chapter_id should be a URL or identifier
            pages_data = self._enma.fetch_chapter_by_symbolic_link(chapter_id)

            if not pages_data:
                return []

            pages = []
            page_list = getattr(pages_data, 'pages', [])

            for i, page in enumerate(page_list):
                url = getattr(page, 'uri', None) or str(page)
                pages.append(PageResult(
                    url=url,
                    index=i,
                    headers={
                        "Referer": "https://manganato.com/",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    },
                    referer="https://manganato.com/"
                ))

            self._handle_success()
            return pages

        except Exception as e:
            self._handle_error(str(e))
            self._log(f"❌ Failed to get pages: {e}")
            return []

    def get_manga_details(self, manga_id: str) -> Optional[MangaResult]:
        """Get detailed manga info."""
        if not self._enma:
            return None

        self._wait_for_rate_limit()

        try:
            manga = self._enma.get(identifier=manga_id)
            if manga:
                self._handle_success()
                return self._manga_to_result(manga)
            return None

        except Exception as e:
            self._handle_error(str(e))
            return None
