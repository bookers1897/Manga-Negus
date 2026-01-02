"""
================================================================================
MangaNegus v3.0 - ComicX.to Connector
================================================================================
Connector for ComicX.to - a newer manga aggregator site.

ComicX.to is a relatively new manga reading site with good uptime and content.
Uses standard HTML scraping with BeautifulSoup.

Author: @bookers1897
License: MIT
================================================================================
"""

from .base import BaseConnector, MangaResult, ChapterResult, PageResult, source_log
from bs4 import BeautifulSoup
from typing import List, Optional
import requests


class ComicXConnector(BaseConnector):
    """
    Connector for ComicX.to manga site.

    Features:
        - Search by title
        - Chapter listings
        - Page image extraction
    """

    id = "comicx"
    name = "ComicX"
    base_url = "https://comicx.to"
    icon = "🎨"

    # URL Detection patterns
    url_patterns = [
        r'https?://(?:www\.)?comicx\.to/comic/([a-z0-9_-]+)',  # e.g., /comic/naruto
    ]

    # Conservative rate limit for new source
    rate_limit = 1.5
    rate_limit_burst = 3
    request_timeout = 20

    supports_latest = False
    supports_popular = False
    requires_cloudflare = False  # May change if they add protection

    languages = ["en"]

    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _headers(self) -> dict:
        """Get request headers."""
        return {
            "User-Agent": self.USER_AGENT,
            "Referer": self.base_url,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

    def _request_html(self, url: str) -> str:
        """Fetch HTML with rate limiting."""
        self._wait_for_rate_limit()

        try:
            resp = self.session.get(
                url,
                headers=self._headers(),
                timeout=self.request_timeout
            )
            resp.raise_for_status()
            self._handle_success()
            return resp.text

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                self._handle_rate_limit()
            raise
        except Exception as e:
            self._handle_error(str(e))
            raise

    def _log(self, msg: str) -> None:
        """Log a message."""
        source_log(f"[ComicX] {msg}")

    # =========================================================================
    # ABSTRACT METHOD IMPLEMENTATIONS
    # =========================================================================

    def search(self, query: str, page: int = 1) -> List[MangaResult]:
        """
        Search for manga on ComicX.to.

        ComicX uses a search endpoint that returns HTML results.
        """
        try:
            search_url = f"{self.base_url}/search"
            params = {"q": query}

            html = self._request_html(f"{search_url}?q={query}")
            soup = BeautifulSoup(html, 'html.parser')

            results = []

            # ComicX typically uses a grid layout for search results
            # Adjust selectors based on actual HTML structure
            for item in soup.select('.comic-item, .manga-card, .search-result-item'):
                try:
                    # Extract manga ID from link
                    link = item.select_one('a[href*="/comic/"]')
                    if not link:
                        continue

                    manga_id = link['href'].replace('/comic/', '').strip('/')

                    # Extract title
                    title_elem = item.select_one('.title, .comic-title, h3, h4')
                    title = title_elem.text.strip() if title_elem else manga_id.replace('-', ' ').title()

                    # Extract cover image
                    img = item.select_one('img')
                    cover_url = None
                    if img:
                        cover_url = img.get('src') or img.get('data-src')
                        if cover_url and not cover_url.startswith('http'):
                            cover_url = self._absolute_url(cover_url)

                    results.append(MangaResult(
                        id=manga_id,
                        title=title,
                        source=self.id,
                        cover_url=cover_url,
                        url=f"{self.base_url}/comic/{manga_id}"
                    ))

                except Exception as e:
                    self._log(f"Failed to parse search result: {e}")
                    continue

            self._log(f"Found {len(results)} results for '{query}'")
            return results

        except Exception as e:
            self._log(f"Search failed: {e}")
            return []

    def get_chapters(self, manga_id: str, language: str = "en") -> List[ChapterResult]:
        """
        Get chapters for a manga.

        Fetches the manga page and extracts chapter list.
        """
        try:
            manga_url = f"{self.base_url}/comic/{manga_id}"
            html = self._request_html(manga_url)
            soup = BeautifulSoup(html, 'html.parser')

            chapters = []

            # ComicX chapter list selectors (adjust based on actual HTML)
            for item in soup.select('.chapter-item, .chapter-row, li.chapter'):
                try:
                    # Extract chapter link
                    link = item.select_one('a')
                    if not link:
                        continue

                    chapter_url = link.get('href')
                    if not chapter_url:
                        continue

                    # Extract chapter ID from URL
                    # Typically: /comic/manga-id/chapter-123
                    chapter_id = chapter_url.strip('/')

                    # Extract chapter number
                    chapter_text = link.text.strip()
                    import re
                    ch_match = re.search(r'chapter[\s\-_]*(\d+(?:\.\d+)?)', chapter_text, re.IGNORECASE)
                    chapter_num = ch_match.group(1) if ch_match else str(len(chapters) + 1)

                    # Extract chapter title (if any)
                    title_elem = item.select_one('.chapter-title, .title')
                    chapter_title = title_elem.text.strip() if title_elem else None

                    chapters.append(ChapterResult(
                        id=chapter_id,
                        chapter=chapter_num,
                        title=chapter_title,
                        language=language,
                        url=self._absolute_url(chapter_url),
                        source=self.id
                    ))

                except Exception as e:
                    self._log(f"Failed to parse chapter: {e}")
                    continue

            # Sort by chapter number
            chapters.sort(key=lambda x: float(x.chapter))

            self._log(f"Found {len(chapters)} chapters for '{manga_id}'")
            return chapters

        except Exception as e:
            self._log(f"Failed to get chapters: {e}")
            return []

    def get_pages(self, chapter_id: str) -> List[PageResult]:
        """
        Get page images for a chapter.

        Fetches chapter page and extracts image URLs.
        """
        try:
            chapter_url = f"{self.base_url}/{chapter_id}"
            html = self._request_html(chapter_url)
            soup = BeautifulSoup(html, 'html.parser')

            pages = []

            # ComicX page image selectors (adjust based on actual HTML)
            # Many sites use a container with multiple img tags
            page_container = soup.select_one('.page-container, .reader-container, #reader')

            if page_container:
                images = page_container.select('img.page-image, img[data-src]')
            else:
                # Fallback: find all images on page
                images = soup.select('img[src*="page"], img[data-src*="page"]')

            for idx, img in enumerate(images):
                try:
                    # Get image URL (handle lazy loading)
                    img_url = img.get('data-src') or img.get('src')

                    if not img_url:
                        continue

                    # Make absolute URL
                    if not img_url.startswith('http'):
                        img_url = self._absolute_url(img_url)

                    pages.append(PageResult(
                        url=img_url,
                        index=idx,
                        referer=chapter_url
                    ))

                except Exception as e:
                    self._log(f"Failed to parse page {idx}: {e}")
                    continue

            self._log(f"Found {len(pages)} pages for chapter")
            return pages

        except Exception as e:
            self._log(f"Failed to get pages: {e}")
            return []
