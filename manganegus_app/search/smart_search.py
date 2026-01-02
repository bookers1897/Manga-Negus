"""
================================================================================
MangaNegus v3.1 - Smart Search Coordinator
================================================================================
Orchestrates parallel source queries, deduplication, and metadata enrichment.

Flow:
  1. Query top 5 sources in parallel (3s instead of 30s sequential)
  2. Deduplicate using fuzzy title matching
  3. Enrich top 10 results with external metadata
  4. Cache for 1 hour
  5. Return unified results

Performance:
  - Cold (no cache): ~5-8 seconds
  - Warm (cached): ~100ms
================================================================================
"""

import asyncio
import logging
from typing import List, Optional, Dict
import time

from sources import get_source_manager
from sources.base import MangaResult
from .deduplicator import SearchDeduplicator, UnifiedSearchResult
from ..metadata.manager import get_metadata_manager
from .cache import SearchCache

logger = logging.getLogger(__name__)


class SmartSearch:
    """
    Smart search orchestrator with parallel queries and metadata enrichment.
    """

    # Top sources to query (based on speed and coverage)
    DEFAULT_SOURCES = [
        'lua-weebcentral',  # Fast, 1170 chapters
        'mangadex',         # Official API, reliable
        'manganato',        # Good coverage
        'mangafire',        # Cloudflare bypass working
        'mangasee',         # Fast scraper
    ]

    def __init__(self):
        """Initialize smart search."""
        self.deduplicator = SearchDeduplicator(similarity_threshold=85.0)
        self.source_manager = get_source_manager()
        self.cache = SearchCache(ttl=3600, max_size=1000)  # 1 hour cache, max 1000 entries

    async def search(
        self,
        query: str,
        limit: int = 10,
        sources: Optional[List[str]] = None,
        enrich_metadata: bool = True
    ) -> List[Dict]:
        """
        Smart search with parallel queries and deduplication.

        Args:
            query: Search query
            limit: Maximum results to return
            sources: List of source IDs to query (None = default top 5)
            enrich_metadata: Whether to fetch external metadata

        Returns:
            List of unified search results with metadata
        """
        start_time = time.time()

        # Select sources
        if sources is None:
            sources = self.DEFAULT_SOURCES

        # Filter to available sources
        available_sources = [
            s for s in sources
            if s in self.source_manager.sources
        ]

        if not available_sources:
            logger.warning("No available sources for search")
            return []

        # CHECK CACHE FIRST
        cached = self.cache.get(query, available_sources)
        if cached:
            logger.info(f"Cache HIT for query '{query}' ({len(cached)} results, took {time.time() - start_time:.3f}s)")
            return cached[:limit]  # Return cached results with limit applied

        logger.info(f"Cache MISS - Smart search for '{query}' across {len(available_sources)} sources")

        # Step 1: Query sources in parallel
        raw_results = await self._parallel_search(query, available_sources)

        logger.info(f"Got {len(raw_results)} raw results from sources")

        # Step 2: Deduplicate
        unified_results = self.deduplicator.deduplicate(raw_results)

        logger.info(f"Deduplicated to {len(unified_results)} unique manga")

        # Step 3: Limit results
        unified_results = unified_results[:limit]

        # Step 4: Enrich with metadata (optional, async)
        if enrich_metadata and unified_results:
            unified_results = await self._enrich_metadata(unified_results)

        elapsed = time.time() - start_time
        logger.info(f"Smart search completed in {elapsed:.2f}s")

        # Convert to dict for JSON serialization
        results = [self._to_dict(result) for result in unified_results]

        # CACHE RESULTS BEFORE RETURNING
        self.cache.set(query, results, available_sources)

        return results

    async def _parallel_search(
        self,
        query: str,
        source_ids: List[str]
    ) -> List[MangaResult]:
        """
        Query multiple sources in parallel.

        Args:
            query: Search query
            source_ids: List of source IDs

        Returns:
            Combined results from all sources
        """
        # Create search tasks
        tasks = []
        for source_id in source_ids:
            source = self.source_manager.sources.get(source_id)
            if source:
                task = self._search_source(source, query)
                tasks.append(task)

        # Execute in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Flatten and filter errors
        all_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Search failed for {source_ids[i]}: {result}")
                continue

            if result:
                all_results.extend(result)

        return all_results

    async def _search_source(
        self,
        source,
        query: str
    ) -> List[MangaResult]:
        """
        Search single source (wrapped for async).

        Args:
            source: Source connector
            query: Search query

        Returns:
            List of manga results
        """
        try:
            # Source search is synchronous, run in thread pool
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                source.search,
                query,
                1  # page
            )

            if not results:
                return []

            # Sources already return MangaResult objects
            return results

        except Exception as e:
            logger.error(f"Source search failed for {source.id}: {e}")
            return []

    async def _enrich_metadata(
        self,
        results: List[UnifiedSearchResult]
    ) -> List[UnifiedSearchResult]:
        """
        Enrich results with external metadata.

        Fetches metadata from AniList, MAL, etc. for top results.

        Args:
            results: Unified search results

        Returns:
            Results with metadata attached
        """
        try:
            metadata_manager = await get_metadata_manager()

            # Enrich first 10 results (to avoid rate limits)
            for result in results[:10]:
                try:
                    metadata = await metadata_manager.get_enriched_metadata(
                        result.title
                    )

                    if metadata:
                        result.metadata = {
                            'rating': metadata.rating,
                            'rating_anilist': metadata.rating_anilist,
                            'rating_mal': metadata.rating_mal,
                            'genres': metadata.genres,
                            'tags': metadata.tags[:10],  # Limit tags
                            'status': metadata.status.value if metadata.status else None,
                            'year': metadata.year,
                            'cover_image': metadata.cover_image,
                            'synopsis': metadata.synopsis[:300] if metadata.synopsis else None,  # Preview
                            'mappings': metadata.mappings
                        }

                        # Update confidence if we got good metadata
                        if len(metadata.mappings) >= 2:
                            result.match_confidence = 95.0

                except Exception as e:
                    logger.warning(f"Metadata enrichment failed for '{result.title}': {e}")
                    continue

        except Exception as e:
            logger.error(f"Metadata enrichment failed: {e}")

        return results

    def _to_dict(self, result: UnifiedSearchResult) -> Dict:
        """
        Convert UnifiedSearchResult to dict for JSON serialization.

        Args:
            result: Unified search result

        Returns:
            Dict representation
        """
        return {
            'title': result.title,
            'primary_source': result.primary_source,
            'primary_source_id': result.primary_source_id,
            'sources': [
                {
                    'source_id': s.source_id,
                    'source_name': s.source_name,
                    'manga_id': s.manga_id,
                    'url': s.url,
                    'chapters': s.chapters,
                    'status': s.status,
                    'priority': s.priority
                }
                for s in result.sources
            ],
            'total_chapters': result.total_chapters,
            'cover_url': result.cover_url,
            'description': result.description,
            'alt_titles': result.alt_titles,
            'metadata': result.metadata,
            'match_confidence': result.match_confidence
        }
