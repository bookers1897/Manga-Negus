"""
================================================================================
MangaNegus v3.0.1 - LibGen Direct Connector
================================================================================
Direct connector to Library Genesis (LibGen) using community Python libraries.

LibGen is one of the largest shadow libraries with 95TB+ of comics/manga.
This connector uses direct API access (not web scraping like Anna's Archive).

IMPLEMENTATION APPROACHES:
  1. libgen-api (pip install libgen-api) - Simple wrapper
  2. libgen-api-enhanced (pip install libgen-api-enhanced) - More features
  3. Direct HTTP requests to LibGen mirrors

This implementation uses direct HTTP requests to avoid external dependencies.

LibGen Mirrors:
  - http://libgen.rs
  - http://libgen.st
  - http://libgen.is

API Endpoints:
  - /search.php?req={query}&res=100&view=simple&phrase=1&column=title
  - /json.php?ids={comma_separated_ids}&fields=*

Author: @bookers1897
License: MIT
================================================================================
"""

import re
import json
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin, quote

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

from .base import (
    BaseConnector, MangaResult, ChapterResult, PageResult, SourceStatus, source_log
)


class LibGenConnector(BaseConnector):
    """
    Direct connector to Library Genesis for manga/comics.

    Uses HTTP requests to LibGen mirrors for fast, reliable access.
    Returns complete volumes/series (CBZ, PDF, EPUB) rather than chapters.

    Differences from Anna's Archive connector:
      - Anna's Archive = Aggregator (scrapes LibGen + Z-Lib + Sci-Hub)
      - LibGen Direct = Direct API access to LibGen only
      - Faster, more reliable, but narrower coverage
    """

    # =========================================================================
    # CONFIGURATION
    # =========================================================================

    id = "libgen"
    name = "Library Genesis"
    icon = "📚"
    is_file_source = True

    # LibGen mirrors (in order of reliability)
    MIRRORS = [
        "http://libgen.rs",
        "http://libgen.st",
        "http://libgen.is"
    ]

    # Use first mirror as base_url
    base_url = MIRRORS[0]

    # URL Detection patterns
    # Use non-capturing group (?:...) for domain, capturing group for ID
    url_patterns = [
        r'https?://(?:www\.)?libgen\.(?:rs|st|is)/book/index\.php\?md5=([A-F0-9]{32})',
        r'https?://(?:www\.)?libgen\.(?:rs|st|is)/comics/\?id=(\d+)',
    ]

    # Conservative rate limit - be respectful to LibGen
    rate_limit = 1.0  # 1 request per second
    rate_limit_burst = 2
    request_timeout = 20

    supports_latest = False  # LibGen doesn't have a "latest" endpoint
    supports_popular = False  # No popularity metrics
    requires_cloudflare = False

    languages = ["en", "ja", "es", "fr", "de", "it", "ru"]  # Multi-language

    USER_AGENT = "MangaNegus/3.0.1 (+https://github.com/bookers1897/Manga-Negus) Research/Education"

    # Content type for comics
    TOPIC_COMICS = "comics"

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _headers(self) -> Dict[str, str]:
        """Get request headers with clear user agent."""
        return {
            "User-Agent": self.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9"
        }

    def _request_html(self, url: str, params: Optional[Dict] = None) -> Optional[str]:
        """Fetch HTML with rate limiting and mirror fallback."""
        if not self.session:
            return None

        self._wait_for_rate_limit()

        # Try each mirror until one works
        for mirror in self.MIRRORS:
            # Replace base URL with current mirror
            mirror_url = url.replace(self.base_url, mirror)

            try:
                resp = self.session.get(
                    mirror_url,
                    params=params,
                    headers=self._headers(),
                    timeout=self.request_timeout
                )

                if resp.status_code == 200:
                    self._handle_success()
                    return resp.text
                elif resp.status_code == 429:
                    self._handle_rate_limit(retry_after=120)
                    continue
                else:
                    continue  # Try next mirror

            except Exception as e:


                self._log(f"Failed to parse item: {e}")


                continue  # Try next mirror

        # All mirrors failed
        self._handle_error("All LibGen mirrors failed")
        return None

    def _log(self, msg: str) -> None:
        """Log a message."""
        source_log(f"[LibGen] {msg}")

    def _parse_search_results(self, html: str) -> List[Dict[str, Any]]:
        """Parse search results from LibGen HTML."""
        if not HAS_BS4:
            return []

        soup = BeautifulSoup(html, 'html.parser')
        results = []

        # LibGen search results are in a table
        # <table> <tr> <td>ID</td> <td>Authors</td> <td>Title</td> ... </tr>
        table = soup.select_one('table.c')
        if not table:
            return []

        rows = table.select('tr')[1:]  # Skip header row

        for row in rows:
            try:
                cols = row.select('td')
                if len(cols) < 10:
                    continue

                # Extract data from columns
                # Column indices (LibGen HTML structure):
                # 0: ID
                # 1: Authors
                # 2: Title
                # 3: Publisher
                # 4: Year
                # 5: Pages
                # 6: Language
                # 7: Size
                # 8: Extension
                # 9: Mirrors (download links)

                book_id = cols[0].get_text(strip=True)
                authors = cols[1].get_text(strip=True)
                title = cols[2].get_text(strip=True)
                publisher = cols[3].get_text(strip=True)
                year = cols[4].get_text(strip=True)
                pages = cols[5].get_text(strip=True)
                language = cols[6].get_text(strip=True)
                size = cols[7].get_text(strip=True)
                extension = cols[8].get_text(strip=True)

                # Extract MD5 from download link
                download_link = cols[9].select_one('a')
                md5 = None
                if download_link:
                    href = download_link.get('href', '')
                    md5_match = re.search(r'md5=([A-F0-9]{32})', href, re.IGNORECASE)
                    if md5_match:
                        md5 = md5_match.group(1).lower()

                # Extract cover URL (if available)
                cover_link = cols[2].select_one('a')
                cover_url = None
                if cover_link:
                    href = cover_link.get('href', '')
                    if '/covers/' in href:
                        cover_url = urljoin(self.base_url, href)

                results.append({
                    'id': book_id,
                    'md5': md5,
                    'title': title,
                    'authors': authors,
                    'publisher': publisher,
                    'year': year,
                    'pages': pages,
                    'language': language,
                    'size': size,
                    'extension': extension.upper(),
                    'cover_url': cover_url
                })

            except Exception as e:
                self._log(f"Failed to parse search result: {e}")
                continue

        return results

    def _get_download_mirrors(self, md5: str) -> List[Dict[str, str]]:
        """Get download mirrors for a file by MD5."""
        if not md5:
            return []

        mirrors = []

        # LibGen has multiple download mirrors
        # Mirror 1: libgen.lc/ads.php?md5={md5}
        mirrors.append({
            'name': 'LibGen.lc',
            'url': f"http://libgen.lc/ads.php?md5={md5}"
        })

        # Mirror 2: libgen.rs/book/index.php?md5={md5}
        mirrors.append({
            'name': 'LibGen.rs',
            'url': f"{self.base_url}/book/index.php?md5={md5}"
        })

        # Mirror 3: cloudflare-ipfs.com (IPFS gateway)
        mirrors.append({
            'name': 'IPFS',
            'url': f"https://cloudflare-ipfs.com/ipfs/{md5}"
        })

        return mirrors

    # =========================================================================
    # ABSTRACT METHOD IMPLEMENTATIONS
    # =========================================================================

    def search(self, query: str, page: int = 1) -> List[MangaResult]:
        """
        Search LibGen for manga/comics.

        Searches in the 'comics' topic for relevant results.
        Returns complete volumes/series (CBZ, PDF, EPUB).
        """
        if not HAS_BS4:
            self._log("⚠️ BeautifulSoup not installed")
            return []

        self._log(f"🔍 Searching LibGen comics: {query}")

        # Build search URL
        # LibGen search params:
        #   req = search query
        #   res = results per page (max 100)
        #   column = search in title
        #   topic = comics
        #   view = simple (HTML table view)
        #   phrase = 1 (exact phrase matching)

        params = {
            'req': query,
            'res': 100,
            'column': 'title',
            'topic': self.TOPIC_COMICS,
            'view': 'simple',
            'phrase': 1,
            'page': page
        }

        html = self._request_html(
            f"{self.base_url}/search.php",
            params=params
        )

        if not html:
            return []

        # Parse search results
        parsed_results = self._parse_search_results(html)

        results = []
        for item in parsed_results[:20]:  # Limit to 20 results
            try:
                # Build description with metadata
                description_parts = []
                if item.get('authors'):
                    description_parts.append(f"Author: {item['authors']}")
                if item.get('year'):
                    description_parts.append(f"Year: {item['year']}")
                if item.get('pages'):
                    description_parts.append(f"Pages: {item['pages']}")
                if item.get('size'):
                    description_parts.append(f"Size: {item['size']}")
                if item.get('extension'):
                    description_parts.append(f"Format: {item['extension']}")

                description = ' | '.join(description_parts) if description_parts else None

                # Use MD5 as ID (more reliable than book ID)
                manga_id = item.get('md5') or item.get('id')

                results.append(MangaResult(
                    id=manga_id,
                    title=item['title'],
                    source=self.id,
                    cover_url=item.get('cover_url'),
                    author=item.get('authors'),
                    description=description,
                    url=f"{self.base_url}/book/index.php?md5={item.get('md5')}" if item.get('md5') else None
                ))

            except Exception as e:
                self._log(f"Failed to parse result: {e}")
                continue

        self._log(f"✅ Found {len(results)} LibGen results")
        return results

    def get_chapters(self, manga_id: str, language: str = "en") -> List[ChapterResult]:
        """
        Get "chapters" for a manga.

        NOTE: LibGen provides complete volumes, not chapters.
        This returns download mirror options as "chapters".

        Each "chapter" represents a different download mirror.
        """
        self._log(f"📖 Fetching download mirrors for {manga_id}...")

        # Get download mirrors for this file
        mirrors = self._get_download_mirrors(manga_id)

        chapters = []
        for idx, mirror in enumerate(mirrors):
            chapters.append(ChapterResult(
                id=f"{manga_id}_{idx}",
                chapter=str(idx + 1),
                title=f"Download from {mirror['name']}",
                language=language,
                url=mirror['url'],
                source=self.id
            ))

        self._log(f"✅ Found {len(chapters)} download mirrors")
        return chapters

    def get_pages(self, chapter_id: str) -> List[PageResult]:
        """
        Get "pages" for a chapter.

        NOTE: LibGen provides download links to files, not individual pages.
        Returns a single "page" with the download URL.

        Users should download the CBZ/PDF/EPUB file and open in a reader.
        """
        try:
            # Extract MD5 and mirror index from chapter_id (format: md5_index)
            parts = chapter_id.rsplit('_', 1)
            if len(parts) != 2:
                return []

            md5, mirror_idx = parts
            mirrors = self._get_download_mirrors(md5)

            if int(mirror_idx) >= len(mirrors):
                return []

            mirror = mirrors[int(mirror_idx)]

            # Return single "page" with download URL
            return [PageResult(
                url=mirror['url'],
                index=0,
                headers={'User-Agent': self.USER_AGENT}
            )]

        except Exception as e:
            self._log(f"Failed to get download URL: {e}")
            return []

    # =========================================================================
    # ADDITIONAL METHODS
    # =========================================================================

    def get_manga_details(self, manga_id: str) -> Optional[MangaResult]:
        """
        Get detailed information about a manga file.

        Fetches metadata from LibGen detail page.
        """
        if not HAS_BS4:
            return None

        try:
            # Build detail page URL
            detail_url = f"{self.base_url}/book/index.php?md5={manga_id}"

            html = self._request_html(detail_url)
            if not html:
                return None

            soup = BeautifulSoup(html, 'html.parser')

            # Extract metadata from detail page
            # LibGen detail pages have a table with metadata rows

            title = None
            author = None
            description = None
            cover_url = None

            # Find title
            title_elem = soup.select_one('h1, .title')
            if title_elem:
                title = title_elem.get_text(strip=True)

            # Find author
            author_row = soup.find('td', string=re.compile(r'Author', re.I))
            if author_row:
                author_cell = author_row.find_next_sibling('td')
                if author_cell:
                    author = author_cell.get_text(strip=True)

            # Find description
            desc_row = soup.find('td', string=re.compile(r'Description', re.I))
            if desc_row:
                desc_cell = desc_row.find_next_sibling('td')
                if desc_cell:
                    description = desc_cell.get_text(strip=True)

            # Find cover
            cover_img = soup.select_one('img[src*="covers"]')
            if cover_img:
                cover_url = urljoin(self.base_url, cover_img.get('src'))

            return MangaResult(
                id=manga_id,
                title=title or f"LibGen Book {manga_id[:8]}",
                source=self.id,
                cover_url=cover_url,
                author=author,
                description=description,
                url=detail_url
            )

        except Exception as e:
            self._log(f"Failed to get manga details: {e}")
            return None
