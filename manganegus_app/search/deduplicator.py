"""
================================================================================
MangaNegus v3.1 - Search Result Deduplicator
================================================================================
Groups duplicate manga from different sources using fuzzy title matching.

Problem:
  User searches "Naruto" → gets 31 results (same manga from 31 sources)

Solution:
  1. Group results by title similarity (85% threshold)
  2. Rank sources by priority (lua-weebcentral > mangadex > manganato...)
  3. Merge chapter counts, URLs, availability
  4. Return unified result with source options

Example Output:
  {
    "title": "Naruto",
    "primary_source": "lua-weebcentral",
    "sources": [
      {"id": "lua-weebcentral", "chapters": 1170, "url": "..."},
      {"id": "mangadex", "chapters": 700, "url": "..."},
      {"id": "manganato", "chapters": 700, "url": "..."}
    ],
    "total_chapters": 1170,  // Highest available
    "metadata": {...}  // From external APIs
  }
================================================================================
"""

from typing import List, Dict, Optional, Set
import logging
from dataclasses import dataclass, field
from rapidfuzz import fuzz

# Import MangaResult from sources (don't duplicate it)
import sys
import os
# Resolve project root dynamically
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
from sources.base import MangaResult

logger = logging.getLogger(__name__)


@dataclass
class SourceOption:
    """A source where this manga is available."""
    source_id: str
    source_name: str
    manga_id: str
    url: Optional[str] = None
    chapters: Optional[int] = None
    status: Optional[str] = None
    priority: int = 5  # 1=highest, 5=lowest


@dataclass
class UnifiedSearchResult:
    """
    Deduplicated search result with multiple source options.

    This is what we return to the frontend.
    """
    # Primary title (from highest priority source)
    title: str

    # All available sources for this manga
    sources: List[SourceOption] = field(default_factory=list)

    # Primary source (highest priority)
    primary_source: str = ""
    primary_source_id: str = ""

    # Aggregated data
    total_chapters: int = 0  # Highest available
    cover_url: Optional[str] = None
    description: Optional[str] = None

    # Alternative titles for display
    alt_titles: List[str] = field(default_factory=list)

    # Metadata from external APIs (populated later)
    metadata: Optional[Dict] = None

    # Confidence score for deduplication (0-100)
    match_confidence: float = 100.0


class SearchDeduplicator:
    """
    Deduplicates search results using fuzzy title matching.

    Algorithm:
      1. Normalize all titles (lowercase, remove special chars)
      2. Group results by similarity (85% threshold)
      3. Within each group, rank sources by priority
      4. Merge into unified result
    """

    # Source priority order (sync with sources/__init__.py)
    SOURCE_PRIORITY = {
        'weebcentral-v2': 1,   # Primary - HTMX breakthrough (curl_cffi)
        'mangadex': 2,         # Secondary - Official API, reliable
        'mangafreak': 3,       # Backup with good coverage
        'mangasee-v2': 4,      # Cloudflare bypass
        'manganato-v2': 5,     # Cloudflare bypass
        'mangafire': 6,        # Solid backup
        'comicx': 7,           # Recent addition
        # Legacy/secondary sources
        'lua-weebcentral': 20,
        'manganato': 21,
        'annas-archive': 22,
        'mangasee': 23,
        'mangahere': 24,
        'mangakakalot': 25,
        'mangakatana': 26,
        'mangapark': 27,
        'mangabuddy': 28,
        'mangareader': 29,
        'asurascans': 30,
        'flamescans': 31,
        'tcbscans': 32,
        'reaperscans': 33,
        'weebcentral': 34,
        'comick': 35,
    }

    # Source display names
    SOURCE_NAMES = {
        'weebcentral-v2': 'WeebCentral',
        'lua-weebcentral': 'WeebCentral',
        'mangadex': 'MangaDex',
        'manganato': 'MangaNato',
        'mangafire': 'MangaFire',
        'annas-archive': "Anna's Archive",
        'comicx': 'ComicX',
        'manganato-v2': 'MangaNato',
        'mangasee-v2': 'MangaSee',
        'mangasee': 'MangaSee',
        'mangahere': 'MangaHere',
        'mangakakalot': 'MangaKakalot',
        'mangafreak': 'MangaFreak',
        'mangakatana': 'MangaKatana',
        'mangapark': 'MangaPark',
        'mangabuddy': 'MangaBuddy',
        'mangareader': 'MangaReader',
        'asurascans': 'AsuraScans',
        'flamescans': 'FlameScans',
        'tcbscans': 'TCB Scans',
        'reaperscans': 'ReaperScans',
    }

    def __init__(self, similarity_threshold: float = 85.0):
        """
        Initialize deduplicator.

        Args:
            similarity_threshold: Minimum similarity for grouping (0-100)
        """
        self.similarity_threshold = similarity_threshold

    def normalize_title(self, title: str) -> str:
        """
        Normalize title for comparison.

        Same logic as metadata matcher:
          - Lowercase
          - Remove special chars
          - Remove articles ("the", "a", "an")
          - Collapse whitespace

        Args:
            title: Raw title

        Returns:
            Normalized title
        """
        import re

        # Lowercase
        title = title.lower()

        # Remove articles
        title = re.sub(r'\b(the|a|an)\b', '', title)

        # Remove special characters (keep alphanumeric and spaces)
        title = re.sub(r'[^a-z0-9\s]', '', title)

        # Collapse whitespace
        title = re.sub(r'\s+', ' ', title)

        # Strip
        return title.strip()

    def calculate_similarity(self, title1: str, title2: str) -> float:
        """
        Calculate similarity between two titles.

        Uses rapidfuzz for fuzzy matching:
          - Basic ratio
          - Token sort ratio (order-independent)
          - Returns highest score

        Args:
            title1: First title
            title2: Second title

        Returns:
            Similarity score (0-100)
        """
        norm1 = self.normalize_title(title1)
        norm2 = self.normalize_title(title2)

        # Basic ratio
        basic = fuzz.ratio(norm1, norm2)

        # Token sort (order-independent)
        token_sort = fuzz.token_sort_ratio(norm1, norm2)

        # Token set (handles partial matches)
        token_set = fuzz.token_set_ratio(norm1, norm2)

        # Return highest score
        return max(basic, token_sort, token_set)

    def deduplicate(
        self,
        results: List[MangaResult]
    ) -> List[UnifiedSearchResult]:
        """
        Deduplicate search results into unified entries.

        Algorithm:
          1. For each result, find all similar titles
          2. Group into clusters
          3. For each cluster, create UnifiedSearchResult
          4. Rank sources by priority

        Args:
            results: Raw search results from sources

        Returns:
            List of deduplicated unified results
        """
        if not results:
            return []

        # Track which results have been grouped
        grouped: Set[int] = set()
        unified_results: List[UnifiedSearchResult] = []

        for i, result in enumerate(results):
            if i in grouped:
                continue

            # Start new group with this result
            group: List[MangaResult] = [result]
            grouped.add(i)

            # Find all similar results
            for j, other in enumerate(results):
                if j <= i or j in grouped:
                    continue

                # Calculate similarity
                similarity = self.calculate_similarity(result.title, other.title)

                if similarity >= self.similarity_threshold:
                    group.append(other)
                    grouped.add(j)
                    logger.debug(
                        f"Grouped '{other.title}' with '{result.title}' "
                        f"(similarity: {similarity:.1f}%)"
                    )

            # Create unified result from group
            unified = self._merge_group(group)
            unified_results.append(unified)

        logger.info(
            f"Deduplicated {len(results)} results into {len(unified_results)} unique manga"
        )

        return unified_results

    def _merge_group(self, group: List[MangaResult]) -> UnifiedSearchResult:
        """
        Merge a group of similar results into unified result.

        Strategy:
          - Use highest priority source as primary
          - Collect all sources as options
          - Use highest chapter count
          - Merge alternative titles

        Args:
            group: List of similar manga results

        Returns:
            Unified search result
        """
        # Sort by source priority
        sorted_group = sorted(
            group,
            key=lambda r: self.SOURCE_PRIORITY.get(r.source, 999)
        )

        # Primary result (highest priority source)
        primary = sorted_group[0]

        # Create source options
        sources = []

        for result in sorted_group:
            source_option = SourceOption(
                source_id=result.source,
                source_name=self.SOURCE_NAMES.get(result.source, result.source),
                manga_id=result.id,
                url=result.url,
                chapters=None,  # Search results don't include chapter counts
                status=result.status,
                priority=self.SOURCE_PRIORITY.get(result.source, 999)
            )
            sources.append(source_option)

        # Collect alternative titles
        alt_titles = []
        for result in sorted_group:
            if result.title != primary.title and result.title not in alt_titles:
                alt_titles.append(result.title)
            for alt in result.alt_titles:
                if alt not in alt_titles and alt != primary.title:
                    alt_titles.append(alt)

        # Create unified result
        return UnifiedSearchResult(
            title=primary.title,
            sources=sources,
            primary_source=self.SOURCE_NAMES.get(primary.source, primary.source),
            primary_source_id=primary.source,
            total_chapters=0,  # Chapter counts fetched separately via get_chapters()
            cover_url=primary.cover_url,
            description=primary.description,
            alt_titles=alt_titles,
            match_confidence=100.0  # Will be updated by metadata matcher
        )
