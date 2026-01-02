"""
================================================================================
MangaNegus v3.0 - Anna's Archive Connector
================================================================================
Connector for Anna's Archive - shadow library aggregator for comics/manga.

Anna's Archive aggregates metadata from:
  - Library Genesis (LibGen)
  - Z-Library (ZLib)
  - Sci-Hub
  - Other shadow libraries

This connector searches for manga/comics and provides download links.
95TB+ of comics from LibGen.li fork are available.

Technical Details:
  - Backend: ElasticSearch (search) + MariaDB (data)
  - Content Type: book_comic for manga/comics
  - MD5-based file identification
  - Multiple mirror options per file

Author: @bookers1897
License: MIT
================================================================================
"""

from .base import BaseConnector, MangaResult, ChapterResult, PageResult, source_log
from bs4 import BeautifulSoup
from typing import List, Optional, Dict
import requests
import json


class AnnasArchiveConnector(BaseConnector):
    """
    Connector for Anna's Archive shadow library aggregator.

    NOTE: This is different from traditional manga sites:
      - Searches for complete manga volumes (CBZ, PDF, EPUB)
      - No traditional "chapters" - instead full series/volumes
      - Provides download links to multiple mirrors
      - MD5-based file identification

    Use Case:
      - Downloading complete manga series
      - Accessing archived/rare manga
      - Multiple format options (CBZ, PDF, EPUB)
    """

    id = "annas-archive"
    name = "Anna's Archive"
    base_url = "https://annas-archive.org"
    icon = "📚"

    # URL Detection patterns
    url_patterns = [
        r'https?://(?:www\.)?annas-archive\.org/md5/([a-f0-9]{32})',  # MD5 hash
        r'https?://(?:www\.)?annas-archive\.org/search\?q=([^&]+)',   # Search query
    ]

    # Conservative rate limit - be respectful to Anna's Archive
    rate_limit = 1.0  # 1 request per second
    rate_limit_burst = 2
    request_timeout = 20

    supports_latest = False
    supports_popular = False
    requires_cloudflare = False

    languages = ["en", "ja", "es", "fr", "de", "it"]  # Multi-language

    USER_AGENT = "MangaNegus/3.0 (+https://github.com/bookers1897/Manga-Negus) Research/Education"

    # Content type filter for comics/manga
    CONTENT_TYPE_COMIC = "book_comic"

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _headers(self) -> dict:
        """Get request headers with clear user agent for archival research."""
        return {
            "User-Agent": self.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9"
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
                self._handle_rate_limit(retry_after=120)  # 2 min cooldown
            raise
        except Exception as e:
            self._handle_error(str(e))
            raise

    def _log(self, msg: str) -> None:
        """Log a message."""
        source_log(f"[Anna's Archive] {msg}")

    def _parse_file_info(self, soup) -> Dict:
        """Extract file information from result page."""
        file_info = {
            'formats': [],
            'size': None,
            'md5': None,
            'mirrors': []
        }

        # Extract file formats
        format_tags = soup.select('.file-format, .format-tag')
        for tag in format_tags:
            fmt = tag.text.strip().upper()
            if fmt in ['CBZ', 'CBR', 'PDF', 'EPUB', 'MOBI']:
                file_info['formats'].append(fmt)

        # Extract file size
        size_elem = soup.select_one('.file-size, .size')
        if size_elem:
            file_info['size'] = size_elem.text.strip()

        # Extract MD5
        md5_elem = soup.select_one('[data-md5], .md5-hash')
        if md5_elem:
            file_info['md5'] = md5_elem.get('data-md5') or md5_elem.text.strip()

        # Extract mirror links
        mirror_links = soup.select('a[href*="download"], a[href*="mirror"]')
        for link in mirror_links:
            mirror_name = link.text.strip()
            mirror_url = link.get('href')
            if mirror_url:
                file_info['mirrors'].append({
                    'name': mirror_name,
                    'url': self._absolute_url(mirror_url)
                })

        return file_info

    # =========================================================================
    # ABSTRACT METHOD IMPLEMENTATIONS
    # =========================================================================

    def search(self, query: str, page: int = 1) -> List[MangaResult]:
        """
        Search for manga/comics on Anna's Archive.

        Searches specifically in the 'book_comic' content type.
        Returns complete volumes/series rather than individual chapters.
        """
        try:
            # Build search URL with content type filter
            search_url = f"{self.base_url}/search"
            params = {
                'q': query,
                'content': self.CONTENT_TYPE_COMIC,  # Filter to comics
                'ext': 'cbz',  # Prefer CBZ format for comics
                'sort': 'newest',
                'page': page - 1  # Anna's Archive uses 0-indexed pages
            }

            # Construct full URL
            param_str = '&'.join([f"{k}={v}" for k, v in params.items()])
            full_url = f"{search_url}?{param_str}"

            self._log(f"Searching for '{query}' in comics...")

            html = self._request_html(full_url)
            soup = BeautifulSoup(html, 'html.parser')

            results = []

            # Anna's Archive search results are typically in a list/grid
            # Adjust selectors based on actual HTML structure
            for item in soup.select('.search-result-item, .book-item, article'):
                try:
                    # Extract link to detail page
                    link = item.select_one('a[href*="/md5/"]')
                    if not link:
                        continue

                    detail_url = link.get('href')
                    # Extract MD5 from URL: /md5/abc123...
                    import re
                    md5_match = re.search(r'/md5/([a-f0-9]{32})', detail_url)
                    if not md5_match:
                        continue

                    md5_hash = md5_match.group(1)

                    # Extract title
                    title_elem = item.select_one('h3, h4, .title, .book-title')
                    title = title_elem.text.strip() if title_elem else f"Comic {md5_hash[:8]}"

                    # Extract metadata
                    author_elem = item.select_one('.author, .creator')
                    author = author_elem.text.strip() if author_elem else None

                    # Extract file info
                    file_info = self._parse_file_info(item)

                    # Extract cover image (if available)
                    img = item.select_one('img')
                    cover_url = None
                    if img:
                        cover_url = img.get('src') or img.get('data-src')
                        if cover_url and not cover_url.startswith('http'):
                            cover_url = self._absolute_url(cover_url)

                    # Build description with file info
                    description_parts = []
                    if file_info['formats']:
                        description_parts.append(f"Formats: {', '.join(file_info['formats'])}")
                    if file_info['size']:
                        description_parts.append(f"Size: {file_info['size']}")
                    if file_info['mirrors']:
                        description_parts.append(f"Mirrors: {len(file_info['mirrors'])}")

                    description = ' | '.join(description_parts) if description_parts else None

                    results.append(MangaResult(
                        id=md5_hash,
                        title=title,
                        source=self.id,
                        cover_url=cover_url,
                        author=author,
                        description=description,
                        url=self._absolute_url(detail_url)
                    ))

                except Exception as e:
                    self._log(f"Failed to parse search result: {e}")
                    continue

            self._log(f"Found {len(results)} comic results for '{query}'")
            return results

        except Exception as e:
            self._log(f"Search failed: {e}")
            return []

    def get_chapters(self, manga_id: str, language: str = "en") -> List[ChapterResult]:
        """
        Get "chapters" for a manga.

        NOTE: Anna's Archive doesn't have traditional chapters.
        Instead, this returns download options (mirrors) as "chapters".

        Each "chapter" represents a different download mirror or format.
        """
        try:
            detail_url = f"{self.base_url}/md5/{manga_id}"
            html = self._request_html(detail_url)
            soup = BeautifulSoup(html, 'html.parser')

            chapters = []

            # Get all download mirrors/options
            download_section = soup.select_one('.download-options, .mirrors, .download-links')

            if download_section:
                mirror_links = download_section.select('a[href*="download"], a[href*="mirror"]')
            else:
                mirror_links = soup.select('a[href*="download"], a[href*="libgen"], a[href*="z-lib"]')

            for idx, link in enumerate(mirror_links):
                try:
                    mirror_name = link.text.strip()
                    mirror_url = link.get('href')

                    if not mirror_url:
                        continue

                    # Extract format from link text or URL
                    import re
                    format_match = re.search(r'\.(cbz|cbr|pdf|epub)', mirror_url.lower())
                    file_format = format_match.group(1).upper() if format_match else "Unknown"

                    # Use mirror name as "chapter" title
                    chapter_title = f"{mirror_name} ({file_format})"

                    chapters.append(ChapterResult(
                        id=f"{manga_id}_{idx}",
                        chapter=str(idx + 1),
                        title=chapter_title,
                        language=language,
                        url=self._absolute_url(mirror_url),
                        source=self.id
                    ))

                except Exception as e:
                    self._log(f"Failed to parse download option: {e}")
                    continue

            self._log(f"Found {len(chapters)} download options for '{manga_id}'")
            return chapters

        except Exception as e:
            self._log(f"Failed to get download options: {e}")
            return []

    def get_pages(self, chapter_id: str) -> List[PageResult]:
        """
        Get "pages" for a chapter.

        NOTE: Anna's Archive provides download links to files, not individual pages.
        This method returns a single "page" with the download URL.

        Users should download the CBZ/PDF file and open it in a reader.
        """
        try:
            # Extract MD5 from chapter_id (format: md5_index)
            md5_hash = chapter_id.rsplit('_', 1)[0]

            # Return single "page" with download info
            pages = [PageResult(
                url=f"{self.base_url}/md5/{md5_hash}",
                index=0,
                headers={'User-Agent': self.USER_AGENT}
            )]

            return pages

        except Exception as e:
            self._log(f"Failed to get download URL: {e}")
            return []

    # =========================================================================
    # ADDITIONAL METHODS
    # =========================================================================

    def get_manga_details(self, manga_id: str) -> Optional[MangaResult]:
        """
        Get detailed information about a manga file.

        Provides comprehensive metadata from Anna's Archive.
        """
        try:
            detail_url = f"{self.base_url}/md5/{manga_id}"
            html = self._request_html(detail_url)
            soup = BeautifulSoup(html, 'html.parser')

            # Extract title
            title_elem = soup.select_one('h1, .title, .book-title')
            title = title_elem.text.strip() if title_elem else f"Comic {manga_id[:8]}"

            # Extract metadata
            author_elem = soup.select_one('.author, .creator')
            author = author_elem.text.strip() if author_elem else None

            # Extract description
            desc_elem = soup.select_one('.description, .summary')
            description = desc_elem.text.strip() if desc_elem else None

            # Extract file info
            file_info = self._parse_file_info(soup)

            # Extract cover
            img = soup.select_one('.cover-image, img[src*="cover"]')
            cover_url = None
            if img:
                cover_url = img.get('src') or img.get('data-src')
                if cover_url and not cover_url.startswith('http'):
                    cover_url = self._absolute_url(cover_url)

            return MangaResult(
                id=manga_id,
                title=title,
                source=self.id,
                cover_url=cover_url,
                author=author,
                description=description,
                url=detail_url
            )

        except Exception as e:
            self._log(f"Failed to get manga details: {e}")
            return None
